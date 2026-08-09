from __future__ import annotations

from typing import Any

from .common import Paths
from .store import verify_installed


def inspect(paths: Paths) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    checks["gpu_map"] = paths.at("/etc/pds4/gpus.conf").is_file()
    checks["release"] = paths.at("/opt/pds4/current").is_symlink()
    models: dict[str, str] = {}
    if paths.models.exists():
        for directory in sorted(paths.models.iterdir()):
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                verify_installed(directory.name, paths)
                models[directory.name] = "verified"
            except Exception as exc:
                models[directory.name] = type(exc).__name__
    checks["models"] = models
    checks["ok"] = bool(
        checks["gpu_map"] and checks["release"] and models
        and all(status == "verified" for status in models.values())
    )
    return checks
