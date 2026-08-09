from __future__ import annotations

import os
import grp
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


def _service_readable(path: pathlib.Path) -> None:
    path.chmod(0o440)
    if os.geteuid() == 0:
        try:
            group = grp.getgrnam("pds4-models").gr_gid
        except KeyError as exc:
            raise PDS4Error("pds4-models group is required before privileged import") from exc
        os.chown(path, 0, group)


def _service_directory(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o750)
    path.chmod(0o750)
    if os.geteuid() == 0:
        try:
            group = grp.getgrnam("pds4-models").gr_gid
        except KeyError as exc:
            raise PDS4Error("pds4-models group is required before privileged import") from exc
        os.chown(path, 0, group)


def _copy_blob(source: pathlib.Path, destination: pathlib.Path, size: int, expected_digest: str) -> None:
    _service_directory(destination.parent)
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
        copied_digest, copied_size = sha256_file(temporary)
        if copied_digest != expected_digest or copied_size != size:
            raise PDS4Error("artifact changed while it was being imported")
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
        if source.is_symlink() or not source.is_file() or source.stat().st_nlink != 1:
            raise PDS4Error(f"artifact is missing or unsafe: {artifact['file']}")
        digest, size = sha256_file(source)
        if digest != artifact["sha256"] or size != artifact["size"]:
            raise PDS4Error(f"artifact verification failed: {artifact['file']}")
        if artifact["role"] == "weights" and source.suffix.casefold() == ".gguf":
            inspect_gguf(source)
        verified.append((source, artifact))
    for source, artifact in verified:
        stored = blob_path(paths, artifact["sha256"])
        _copy_blob(source, stored, artifact["size"], artifact["sha256"])
        _service_readable(stored)
    installed = dict(manifest)
    installed["status"] = "verified"
    target = paths.models / manifest["id"] / "manifest.json"
    _service_directory(target.parent)
    atomic_write(target, canonical_json(installed), 0o440)
    _service_readable(target)
    model_directory = target.parent
    for artifact in installed["artifacts"]:
        destination = model_directory / artifact["file"]
        temporary = model_directory / f".{artifact['file']}.link"
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(blob_path(paths, artifact["sha256"]))
        os.replace(temporary, destination)
        if artifact["role"] == "weights":
            model_link = model_directory / ".model.gguf.link"
            model_link.unlink(missing_ok=True)
            model_link.symlink_to(blob_path(paths, artifact["sha256"]))
            os.replace(model_link, model_directory / "model.gguf")
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
