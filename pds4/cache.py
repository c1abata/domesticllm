from __future__ import annotations

import os
import pathlib
import re
import shutil
import tempfile
import time
from typing import Any

from .common import Paths, PDS4Error, atomic_write, canonical_json, read_json, sha256_file
from .manifest import HEX64, REVISION


SESSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
IDENTITY_FIELDS = (
    "model_sha256", "runtime_commit", "tokenizer_fingerprint", "chat_template_fingerprint",
    "context", "kv_format", "kv_quantization", "steering_fingerprint", "session_id", "lane",
)


def validate_identity(value: Any, session_id: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or any(name not in value for name in IDENTITY_FIELDS):
        raise PDS4Error("KV identity is incomplete")
    if not HEX64.fullmatch(value["model_sha256"]):
        raise PDS4Error("invalid KV model fingerprint")
    if not REVISION.fullmatch(value["runtime_commit"]):
        raise PDS4Error("invalid KV runtime commit")
    for name in ("tokenizer_fingerprint", "chat_template_fingerprint", "steering_fingerprint"):
        if not HEX64.fullmatch(value[name]):
            raise PDS4Error(f"invalid KV {name}")
    if not isinstance(value["context"], int) or isinstance(value["context"], bool) or value["context"] < 1:
        raise PDS4Error("invalid KV context")
    if value["lane"] not in {"flash", "fast"} or not SESSION.fullmatch(value["session_id"]):
        raise PDS4Error("invalid KV lane or session id")
    if session_id is not None and value["session_id"] != session_id:
        raise PDS4Error("KV session id mismatch")
    return value


def _checkpoint_dir(paths: Paths, identity: dict[str, Any]) -> pathlib.Path:
    return paths.at(f"/var/cache/pds4/kv/{identity['lane']}/{identity['session_id']}")


def _session_identity(paths: Paths, session_id: str) -> dict[str, Any]:
    return validate_identity(read_json(paths.state / "sessions" / f"{session_id}.json"), session_id)


def register(paths: Paths, identity: dict[str, Any]) -> None:
    identity = validate_identity(identity)
    atomic_write(paths.state / "sessions" / f"{identity['session_id']}.json",
                 canonical_json(identity), 0o640)


def checkpoint(paths: Paths, session_id: str) -> dict[str, Any]:
    identity = _session_identity(paths, session_id)
    if "cyber" in identity.get("model_id", ""):
        raise PDS4Error("Cyber sessions are ephemeral and cannot be checkpointed")
    live = paths.at(f"/run/pds4/sessions/{session_id}/payload.kv")
    if live.is_symlink() or not live.is_file():
        raise PDS4Error("live KV payload is unavailable")
    target = _checkpoint_dir(paths, identity)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise PDS4Error("checkpoint already exists")
    temporary = pathlib.Path(tempfile.mkdtemp(prefix=f".{session_id}.", dir=target.parent))
    try:
        payload = temporary / "payload.kv"
        with live.open("rb") as source, payload.open("xb") as destination:
            shutil.copyfileobj(source, destination, 8 * 1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        digest, size = sha256_file(payload)
        metadata = dict(identity)
        metadata.update({"schema": 1, "payload_sha256": digest, "payload_size": size,
                         "created_ns": time.time_ns(), "last_access_ns": time.time_ns(), "pinned": False})
        atomic_write(temporary / "metadata.json", canonical_json(metadata), 0o440)
        os.replace(temporary, target)
        return metadata
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def inspect(paths: Paths, session_id: str) -> dict[str, Any]:
    identity = _session_identity(paths, session_id)
    metadata = read_json(_checkpoint_dir(paths, identity) / "metadata.json")
    validate_identity(metadata, session_id)
    return metadata


def verify_checkpoint(paths: Paths, session_id: str) -> dict[str, Any]:
    current = _session_identity(paths, session_id)
    metadata = inspect(paths, session_id)
    for name in IDENTITY_FIELDS:
        if metadata[name] != current[name]:
            raise PDS4Error(f"KV identity changed: {name}")
    payload = _checkpoint_dir(paths, current) / "payload.kv"
    digest, size = sha256_file(payload)
    if digest != metadata.get("payload_sha256") or size != metadata.get("payload_size"):
        raise PDS4Error("KV payload checksum mismatch")
    return metadata


def restore(paths: Paths, session_id: str) -> pathlib.Path:
    metadata = verify_checkpoint(paths, session_id)
    source = _checkpoint_dir(paths, metadata) / "payload.kv"
    live_dir = paths.at(f"/run/pds4/sessions/{session_id}")
    live_dir.mkdir(parents=True, exist_ok=True)
    target = live_dir / "payload.kv"
    descriptor, name = tempfile.mkstemp(prefix=".restore-", dir=live_dir)
    temporary = pathlib.Path(name)
    try:
        with source.open("rb") as input_file, os.fdopen(descriptor, "wb") as output_file:
            shutil.copyfileobj(input_file, output_file, 8 * 1024 * 1024)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    metadata["last_access_ns"] = time.time_ns()
    atomic_write(_checkpoint_dir(paths, metadata) / "metadata.json", canonical_json(metadata), 0o440)
    return target


def list_checkpoints(paths: Paths) -> list[dict[str, Any]]:
    root = paths.at("/var/cache/pds4/kv")
    if not root.exists():
        return []
    result = []
    for metadata_path in sorted(root.glob("*/*/metadata.json")):
        try:
            result.append(validate_identity(read_json(metadata_path)))
        except PDS4Error:
            result.append({"session_id": metadata_path.parent.name, "lane": metadata_path.parent.parent.name,
                           "status": "corrupt"})
    return result


def parse_size(value: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)([KMGTP]?)", value.upper())
    if not match:
        raise PDS4Error("invalid size; use bytes or K/M/G/T/P suffix")
    return int(match.group(1)) * 1024 ** " KMGTP".index(match.group(2))


def prune(paths: Paths, maximum: int) -> list[str]:
    checkpoints = []
    for metadata in list_checkpoints(paths):
        if metadata.get("status") == "corrupt":
            continue
        target = _checkpoint_dir(paths, metadata)
        size = sum(item.stat().st_size for item in target.iterdir() if item.is_file() and not item.is_symlink())
        checkpoints.append((metadata.get("last_access_ns", 0), metadata, target, size))
    total = sum(item[3] for item in checkpoints)
    removed: list[str] = []
    for _, metadata, target, size in sorted(checkpoints):
        if total <= maximum:
            break
        session_id = metadata["session_id"]
        if metadata.get("pinned") or paths.at(f"/run/pds4/sessions/{session_id}").exists():
            continue
        shutil.rmtree(target)
        total -= size
        removed.append(session_id)
    if total > maximum:
        raise PDS4Error("cache quota cannot be met without deleting active or pinned checkpoints")
    return removed
