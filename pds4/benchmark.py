from __future__ import annotations

import hashlib
import http.client
import json
import pathlib
import subprocess
import time
import urllib.parse
import uuid
from typing import Any

from .common import Paths, PDS4Error, atomic_write, canonical_json
from .store import verify_installed


def hardware_snapshot() -> list[dict[str, Any]]:
    command = ["nvidia-smi", "--query-gpu=uuid,memory.used,temperature.gpu,power.draw",
               "--format=csv,noheader,nounits"]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise PDS4Error("cannot capture NVIDIA hardware state") from exc
    gpus = []
    for line in result.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 4 or not fields[0].startswith("GPU-"):
            raise PDS4Error("invalid nvidia-smi benchmark record")
        try:
            gpus.append({"uuid": fields[0], "memory_used_mib": int(fields[1]),
                         "temperature_c": int(fields[2]), "power_w": float(fields[3])})
        except ValueError as exc:
            raise PDS4Error("non-numeric NVIDIA benchmark field") from exc
    return gpus


def _key(path: pathlib.Path) -> str:
    info = path.lstat()
    if path.is_symlink() or info.st_mode & 0o037:
        raise PDS4Error("benchmark key file permissions are too broad")
    value = path.read_text(encoding="utf-8").splitlines()[0]
    if len(value) < 32:
        raise PDS4Error("invalid benchmark API key")
    return value


def run_request(url: str, key_file: pathlib.Path, model: str, prompt: bytes,
                context: int, maximum_tokens: int) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.query:
        raise PDS4Error("benchmark endpoint must be loopback HTTP")
    try:
        prompt_text = prompt.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PDS4Error("benchmark prompt must be UTF-8") from exc
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt_text}],
                          "max_tokens": maximum_tokens, "temperature": 0, "stream": True,
                          "stream_options": {"include_usage": True}}, separators=(",", ":")).encode()
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 8080, timeout=1800)
    started = time.monotonic_ns()
    first_token = None
    usage: dict[str, Any] = {}
    events = 0
    try:
        connection.request("POST", parsed.path, body=payload,
                           headers={"Authorization": "Bearer " + _key(key_file),
                                    "Content-Type": "application/json", "Accept": "text/event-stream"})
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise PDS4Error(f"benchmark request returned HTTP {response.status}")
        while line := response.readline():
            if not line.startswith(b"data:"):
                continue
            raw = line[5:].strip()
            if raw in {b"", b"[DONE]"}:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event.get("usage"):
                usage = event["usage"]
            choices = event.get("choices") or []
            if choices and (choices[0].get("delta") or {}).get("content"):
                events += 1
                first_token = first_token or time.monotonic_ns()
    finally:
        connection.close()
    finished = time.monotonic_ns()
    if first_token is None:
        raise PDS4Error("benchmark stream contained no output token")
    return {"ttft_ms": (first_token - started) / 1_000_000,
            "duration_ms": (finished - started) / 1_000_000,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens", events),
            "stream_events": events, "context": context, "max_tokens": maximum_tokens}


def record(paths: Paths, model_id: str, prompt: bytes, measurements: list[dict[str, Any]],
           hardware: list[dict[str, Any]], output: pathlib.Path) -> dict[str, Any]:
    manifest = verify_installed(model_id, paths)
    weights = next(item for item in manifest["artifacts"] if item["role"] == "weights")
    result = {
        "schema": 1, "id": str(uuid.uuid4()), "created_ns": time.time_ns(),
        "model_id": model_id, "model_sha256": weights["sha256"],
        "runtime_engine": manifest["runtime"]["engine"], "runtime_commit": manifest["runtime"]["commit"],
        "lane": manifest["lane"], "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "measurements": measurements, "hardware": hardware,
        "claim": "measurement-only; no automatic promotion",
    }
    atomic_write(output, canonical_json(result), 0o440)
    return result


def plan() -> dict[str, Any]:
    return {
        "flash": [
            {"context": 32768, "expert_cache": "6G", "status": "baseline"},
            {"context": 32768, "expert_cache": "8G", "status": "experiment"},
            {"context": 65536, "expert_cache": "calibrated", "status": "hardware-gated"},
            {"context": 100000, "expert_cache": "calibrated", "status": "soak-gated"},
        ],
        "fast": [{"context": 16384, "gpu_resident": True, "status": "baseline"}],
        "cpu_partial_offload": {"status": "experimental", "promotion": "measured capacity or speed improvement"},
    }
