#!/usr/bin/env python3
"""Fail closed unless the current interpreter exactly matches requirements.lock."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re
import runpy
import sys


ROOT = Path(__file__).resolve().parent
LOCK = ROOT / "requirements.lock"
REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:[0-9a-f]{64}$")


def verify() -> list[str]:
    failures: list[str] = []
    for raw in LOCK.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        match = REQUIREMENT.fullmatch(raw)
        if not match:
            failures.append(f"invalid locked requirement: {raw}")
            continue
        package, expected = match.groups()
        try:
            actual = version(package)
        except PackageNotFoundError:
            failures.append(f"missing {package}=={expected}")
            continue
        if actual != expected:
            failures.append(f"{package}: expected {expected}, got {actual}")
    return failures


def main() -> None:
    failures = verify()
    if failures:
        raise SystemExit("locked MCP environment mismatch:\n" + "\n".join(failures))
    if sys.argv[1:] == ["--check"]:
        print("locked MCP environment OK")
        return
    if sys.argv[1:]:
        raise SystemExit("usage: locked_launcher.py [--check]")
    runpy.run_path(str(ROOT / "local_ai_server.py"), run_name="__main__")


if __name__ == "__main__":
    main()
