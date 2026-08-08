from __future__ import annotations

import os
import pathlib
import shutil
import struct
import tempfile
from typing import Any

from .common import Paths, PDS4Error, atomic_write, canonical_json, copy_exact, read_json, sha256_file
from .manifest import validate_manifest


def inspect_gguf(path: pathlib.Path) -> dict[str, int]:
    if path.is_symlink() or not path.is_file():
        raise PDS4Error(f"GGUF is not a regular file: {path}")
    with path.open("rb") as source:
        header = source.read(24)
    if len(header) != 24 or header[:4] != b"GGUF":
        raise PDS4Error(f"invalid GGUF header: {path.name}")
    version, tensors, metadata = struct.unpack("<IQQ", header[4:])
    if version not in {2, 3} or tensors > 10_000_000 or metadata > 1_000_000:
        raise PDS4Error(f"unsafe or unsupported GGUF header: {path.name}")
    return {"version": version, "tensor_count": tensors, "metadata_count": metadata}


def blob_path(paths: Paths, digest: str) -> pathlib.Path:
    return paths.store / digest[:2] / digest[2:]


def _copy_blob(source: pathlib.Path, destination: pathlib.Path, size: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        digest, actual_size = sha256_file(destination)
        if digest == destination.parent.name + destination.name and actual_size == size:
            return
        raise PDS4Error(f"content-address collision at {destination}")
    descriptor, name = tempfile.mkstemp(prefix=".import-", dir=destination.parent)
    temporary = pathlib.Path(name)
    try:
        os.fchmod(descriptor, 0o440)
        with source.open("rb") as input_file, os.fdopen(descriptor, "wb") as output_file:
            copy_exact(input_file, output_file, size)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def import_model(manifest_path: pathlib.Path, artifact_dir: pathlib.Path, paths: Paths) -> dict[str, Any]:
    manifest = validate_manifest(read_json(manifest_path))
    if artifact_dir.is_symlink() or not artifact_dir.is_dir():
        raise PDS4Error("artifact directory is not a regular directory")
    verified: list[tuple[pathlib.Path, dict[str, Any]]] = []
    for artifact in manifest["artifacts"]:
        source = artifact_dir / artifact["file"]
        if source.is_symlink() or not source.is_file():
            raise PDS4Error(f"artifact is missing or unsafe: {artifact['file']}")
        digest, size = sha256_file(source)
        if digest != artifact["sha256"] or size != artifact["size"]:
            raise PDS4Error(f"artifact verification failed: {artifact['file']}")
        if artifact["role"] == "weights" and source.suffix.casefold() == ".gguf":
            inspect_gguf(source)
        verified.append((source, artifact))
    for source, artifact in verified:
        _copy_blob(source, blob_path(paths, artifact["sha256"]), artifact["size"])
    installed = dict(manifest)
    installed["status"] = "verified"
    target = paths.models / manifest["id"] / "manifest.json"
    atomic_write(target, canonical_json(installed), 0o440)
    return installed


def verify_installed(model_id: str, paths: Paths) -> dict[str, Any]:
    manifest = validate_manifest(read_json(paths.models / model_id / "manifest.json"))
    for artifact in manifest["artifacts"]:
        target = blob_path(paths, artifact["sha256"])
        digest, size = sha256_file(target)
        if digest != artifact["sha256"] or size != artifact["size"]:
            raise PDS4Error(f"stored artifact failed verification: {artifact['file']}")
    return manifest


def quarantine(source: pathlib.Path, reason: str, paths: Paths) -> pathlib.Path:
    paths.quarantine.mkdir(parents=True, exist_ok=True)
    destination = paths.quarantine / f"{source.name}.{os.getpid()}.bad"
    shutil.move(source, destination)
    atomic_write(destination.with_suffix(destination.suffix + ".reason"), (reason + "\n").encode(), 0o440)
    return destination
