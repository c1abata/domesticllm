#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=vendor-lib.sh
. "$ROOT/scripts/vendor-lib.sh"
prepare_build_dirs
checkout_locked_repo ds4 "$DS4_REPO_URL" "$DS4_COMMIT"
run_build make -C "$REPOS/ds4" cpu

for bin in ds4 ds4-server ds4-bench ds4-agent; do
  if [ -x "$REPOS/ds4/$bin" ]; then
    install -m 0755 "$REPOS/ds4/$bin" "$LOCAL_AI_HOME/bin/$bin"
  fi
done

echo "[ok] ds4 CPU reference build installed for diagnostics"
echo "[note] for Intel CPU serving, use llama-server with the DS4 GGUF profile"
