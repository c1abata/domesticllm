#!/usr/bin/env bash
set -euo pipefail

CUDA_ARCH_NVCC="${CUDA_ARCH_NVCC:-sm_86}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=vendor-lib.sh
. "$ROOT/scripts/vendor-lib.sh"
prepare_build_dirs
command -v nvcc >/dev/null 2>&1 || {
  echo "nvcc not found. Install the NVIDIA CUDA Toolkit first." >&2
  exit 1
}

checkout_locked_repo ds4 "$DS4_REPO_URL" "$DS4_COMMIT"
run_build make -C "$REPOS/ds4" -j"$(nproc)" cuda CUDA_ARCH="$CUDA_ARCH_NVCC"

for bin in ds4 ds4-server ds4-bench ds4-eval ds4-agent; do
  if [ -x "$REPOS/ds4/$bin" ]; then
    install -m 0755 "$REPOS/ds4/$bin" "$LOCAL_AI_HOME/bin/$bin"
  fi
done

if [ -e "$LOCAL_AI_HOME/models/ds4flash.gguf" ]; then
  ln -sfn "$LOCAL_AI_HOME/models/ds4flash.gguf" "$REPOS/ds4/ds4flash.gguf"
fi

echo "[ok] ds4 CUDA reference build installed"
echo "[info] native DS4 CUDA arch: $CUDA_ARCH_NVCC"
