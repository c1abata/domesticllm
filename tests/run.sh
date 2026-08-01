#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"

if ! "$PYTHON" -B mcp/locked_launcher.py --check >/dev/null 2>&1; then
  if [ "${SKIP_MCP_RUNTIME:-0}" != 1 ]; then
    echo "[fail] locked MCP environment unavailable; create .venv-mcp or set SKIP_MCP_RUNTIME=1 for partial host checks" >&2
    exit 1
  fi
  echo "[pending] dynamic MCP tests explicitly skipped on this host"
fi

echo "[check] bash syntax"
while IFS= read -r script; do
  bash -n "$script"
done < <(find scripts tests -type f -name '*.sh' -print)

if command -v shellcheck >/dev/null 2>&1; then
  echo "[check] shellcheck"
  # Source paths are resolved from the repository root.
  shellcheck -S warning -x scripts/*.sh tests/*.sh
else
  echo "[skip] shellcheck not installed"
fi

echo "[check] python unit/static tests"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s tests -p 'test_*.py'

echo "[check] DS4 runtime policy"
bash tests/test_ds4_runtime.sh

if command -v systemd-analyze >/dev/null 2>&1; then
  echo "[check] systemd unit syntax"
  unit_tmp="$(mktemp -d)"
  trap 'rm -rf -- "$unit_tmp"' EXIT
  cp systemd/*.service "$unit_tmp/"
  chmod 0644 "$unit_tmp"/*.service
  set +e
  verify_output="$(systemd-analyze verify "$unit_tmp"/*.service 2>&1)"
  verify_status=$?
  set -e
  unexpected="$(printf '%s\n' "$verify_output" | grep -Ev '^(.*: Command .* is not executable: No such file or directory)?$' || true)"
  if [ "$verify_status" -ne 0 ] && [ -n "$unexpected" ]; then
    printf '%s\n' "$verify_output" >&2
    exit "$verify_status"
  fi
  if [ "$verify_status" -ne 0 ]; then
    echo "[pending] systemd target executables are not installed on this host"
  fi
  rm -rf -- "$unit_tmp"
  trap - EXIT
else
  echo "[skip] systemd-analyze unavailable"
fi

echo "[ok] repository checks passed"
