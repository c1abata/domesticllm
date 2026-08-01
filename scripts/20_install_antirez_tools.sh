#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=vendor-lib.sh
. "$ROOT/scripts/vendor-lib.sh"
prepare_build_dirs

# Critical-path tools only. Optional experiments are deliberately not cloned.
checkout_locked_repo linenoise "$LINENOISE_REPO_URL" "$LINENOISE_COMMIT"
checkout_locked_repo sds "$SDS_REPO_URL" "$SDS_COMMIT"
checkout_locked_repo ds4-gguf-tools "$DS4_REPO_URL" "$DS4_COMMIT"

if [ -f "$REPOS/ds4-gguf-tools/gguf-tools/Makefile" ]; then
  run_build make -C "$REPOS/ds4-gguf-tools/gguf-tools" -j"$(nproc)"
  quantizer="$REPOS/ds4-gguf-tools/gguf-tools/deepseek4-quantize"
  [ -x "$quantizer" ] || { echo "Missing expected gguf-tools binary: $quantizer" >&2; exit 1; }
  install -o root -g root -m 0755 "$quantizer" "$LOCAL_AI_HOME/bin/deepseek4-quantize"
fi

echo "[ok] locked critical Antirez tools prepared"
echo "[note] kilo, botlib, PixelWall and qwen-asr are optional and not in the autonomous path"
