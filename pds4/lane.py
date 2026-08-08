from __future__ import annotations

import fcntl
import http.client
import json
import os
import pathlib
import subprocess
import time
from collections.abc import Callable
from typing import Any

from .common import Paths, PDS4Error, atomic_write, canonical_json, read_json
from .manifest import ID_PATTERN
from .store import blob_path, verify_installed


class Systemctl:
    def __call__(self, action: str, unit: str) -> None:
        if action not in {"start", "stop", "restart"} or not unit.startswith("pds4-"):
            raise PDS4Error("invalid service operation")
        try:
            subprocess.run(["systemctl", action, unit], check=True, timeout=1800)
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            raise PDS4Error(f"systemctl {action} failed for {unit}") from exc


def _audit(paths: Paths, event: dict[str, Any]) -> None:
    target = paths.at("/var/log/pds4/audit.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.is_symlink():
        raise PDS4Error("audit log must not be a symlink")
    record = dict(event)
    record["time_ns"] = time.time_ns()
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o640)
    try:
        os.write(descriptor, canonical_json(record))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _state(paths: Paths, name: str) -> pathlib.Path:
    return paths.state / "lanes" / f"{name}.json"


def read_lane_state(paths: Paths, name: str) -> dict[str, Any]:
    target = _state(paths, name)
    if not target.exists():
        return {"lane": name, "status": "stopped", "model": None}
    value = read_json(target)
    if not isinstance(value, dict) or value.get("lane") != name:
        raise PDS4Error(f"invalid {name} lane state")
    return value


def write_lane_state(paths: Paths, name: str, status: str, model: str | None,
                     error: str | None = None) -> dict[str, Any]:
    value = {"schema": 1, "lane": name, "status": status, "model": model, "updated_ns": time.time_ns()}
    if error:
        value["error"] = error
    atomic_write(_state(paths, name), canonical_json(value), 0o640)
    runtime = paths.at("/run/pds4/routes.json")
    flash = read_lane_state(paths, "flash") if name != "flash" else value
    fast = read_lane_state(paths, "fast") if name != "fast" else value
    atomic_write(runtime, canonical_json({"schema": 1, "flash": flash, "fast": fast}), 0o640)
    return value


def http_probe(port: int, model: str, key: str | None = None) -> None:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Reply only OK"}],
                       "max_tokens": 8, "temperature": 0})
    try:
        connection.request("POST", "/v1/chat/completions", body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read(1024 * 1024)
        if not 200 <= response.status < 300 or b"OK" not in payload:
            raise PDS4Error(f"smoke test failed on port {port}")
    except OSError as exc:
        raise PDS4Error(f"backend unavailable on port {port}") from exc
    finally:
        connection.close()


def _fast_environment(manifest: dict[str, Any], paths: Paths, port: int) -> bytes:
    weights = next(item for item in manifest["artifacts"] if item["role"] == "weights")
    context = 8192 if manifest["id"] == "dolphin-cyber-8b-q4" else min(manifest["context_tested"], 16384)
    values = {
        "PDS4_FAST_MODEL": str(blob_path(paths, weights["sha256"])),
        "PDS4_FAST_ALIAS": manifest["id"], "PDS4_FAST_HOST": "127.0.0.1",
        "PDS4_FAST_PORT": str(port), "PDS4_FAST_CONTEXT": str(context),
        "PDS4_FAST_TOKENS": "4096", "PDS4_FAST_THREADS": "16", "PDS4_FAST_BATCH": "512",
        "PDS4_FAST_UBATCH": "128", "PDS4_FAST_CACHE_K": "q8_0", "PDS4_FAST_CACHE_V": "q8_0",
    }
    return "".join(f"{name}={value}\n" for name, value in values.items()).encode()


def _promote_manifest(model_id: str, paths: Paths) -> None:
    target = paths.models / model_id / "manifest.json"
    manifest = read_json(target)
    manifest["status"] = "promoted"
    atomic_write(target, canonical_json(manifest), 0o440)


def switch_fast(model_id: str, paths: Paths, runner: Callable[[str, str], None] | None = None,
                probe: Callable[[int, str, str | None], None] | None = None,
                api_key: str | None = None) -> dict[str, Any]:
    if not ID_PATTERN.fullmatch(model_id):
        raise PDS4Error("invalid fast model id")
    manifest = verify_installed(model_id, paths)
    if manifest["lane"] != "fast":
        raise PDS4Error("requested model does not belong to the fast lane")
    run = runner or Systemctl()
    check = probe or http_probe
    lock_path = paths.at("/run/pds4/fast.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PDS4Error("another fast lane transaction is active") from exc
        previous = read_lane_state(paths, "fast")
        previous_model = previous.get("model") if previous.get("status") == "ready" else None
        write_lane_state(paths, "fast", "warming", model_id)
        _audit(paths, {"operation": "fast-switch", "phase": "begin", "requested": model_id,
                       "previous": previous_model})
        candidate = f"pds4-fast-canary@{model_id}.service"
        primary = f"pds4-fast@{model_id}.service"
        try:
            if previous_model:
                run("stop", f"pds4-fast@{previous_model}.service")
            atomic_write(paths.at("/run/pds4/fast-canary.env"), _fast_environment(manifest, paths, 8086), 0o640)
            run("start", candidate)
            check(8086, model_id, api_key)
            run("stop", candidate)
            atomic_write(paths.at("/etc/pds4/lanes/fast.env"), _fast_environment(manifest, paths, 8085), 0o640)
            run("start", primary)
            check(8085, model_id, api_key)
            _promote_manifest(model_id, paths)
            state = write_lane_state(paths, "fast", "ready", model_id)
            _audit(paths, {"operation": "fast-switch", "phase": "commit", "requested": model_id})
            return state
        except Exception as exc:
            for unit in (candidate, primary):
                try:
                    run("stop", unit)
                except Exception:
                    pass
            if previous_model:
                previous_manifest = verify_installed(previous_model, paths)
                atomic_write(paths.at("/etc/pds4/lanes/fast.env"),
                             _fast_environment(previous_manifest, paths, 8085), 0o640)
                run("start", f"pds4-fast@{previous_model}.service")
                check(8085, previous_model, api_key)
                state = write_lane_state(paths, "fast", "ready", previous_model,
                                         f"rollback after {type(exc).__name__}")
            else:
                state = write_lane_state(paths, "fast", "failed", None, type(exc).__name__)
            _audit(paths, {"operation": "fast-switch", "phase": "rollback", "requested": model_id,
                           "restored": previous_model, "error": type(exc).__name__})
            raise PDS4Error(f"fast switch failed; restored {previous_model or 'stopped state'}") from exc


def flash_action(action: str, paths: Paths, runner: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    if action not in {"start", "stop"}:
        raise PDS4Error("flash action must be start or stop")
    (runner or Systemctl())(action, "pds4-flash.service")
    return write_lane_state(paths, "flash", "ready" if action == "start" else "stopped",
                            "flash-q2" if action == "start" else None)
