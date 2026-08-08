from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
from dataclasses import dataclass
from typing import Any, BinaryIO


class PDS4Error(RuntimeError):
    pass


def sha256_file(path: pathlib.Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def atomic_write(path: pathlib.Path, payload: bytes, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = pathlib.Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: pathlib.Path, maximum: int = 4 * 1024 * 1024) -> Any:
    if path.is_symlink() or not path.is_file():
        raise PDS4Error(f"not a regular file: {path}")
    if path.stat().st_size > maximum:
        raise PDS4Error(f"JSON file is too large: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PDS4Error(f"invalid JSON: {path}") from exc


def copy_exact(source: BinaryIO, destination: BinaryIO, expected_size: int) -> None:
    remaining = expected_size
    while remaining:
        chunk = source.read(min(8 * 1024 * 1024, remaining))
        if not chunk:
            raise PDS4Error("artifact ended before its declared size")
        destination.write(chunk)
        remaining -= len(chunk)
    if source.read(1):
        raise PDS4Error("artifact exceeds its declared size")


@dataclass(frozen=True)
class Paths:
    prefix: pathlib.Path = pathlib.Path("/")

    def at(self, absolute: str) -> pathlib.Path:
        return self.prefix / absolute.lstrip("/")

    @property
    def store(self) -> pathlib.Path:
        return self.at("/srv/pds4/store/sha256")

    @property
    def models(self) -> pathlib.Path:
        return self.at("/srv/pds4/models")

    @property
    def quarantine(self) -> pathlib.Path:
        return self.at("/srv/pds4/quarantine")

    @property
    def state(self) -> pathlib.Path:
        return self.at("/var/lib/pds4")

    @classmethod
    def environment(cls) -> "Paths":
        return cls(pathlib.Path(os.environ.get("PDS4_ROOT", "/")).resolve())
