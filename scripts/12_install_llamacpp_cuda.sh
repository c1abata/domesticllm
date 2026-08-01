#!/usr/bin/env bash
set -euo pipefail

CUDA_ARCH="${CUDA_ARCH:-86}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=vendor-lib.sh
. "$ROOT/scripts/vendor-lib.sh"
prepare_build_dirs
command -v nvcc >/dev/null 2>&1 || {
  cat >&2 <<'EOF'
nvcc not found. Install the NVIDIA CUDA Toolkit first, then rerun.
Keep the display driver and CUDA toolkit from compatible NVIDIA releases.
EOF
  exit 1
}

checkout_locked_repo llama.cpp "$LLAMA_REPO_URL" "$LLAMA_COMMIT"
run_build cmake -S "$REPOS/llama.cpp" -B "$REPOS/llama.cpp/build-cuda" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_CUDA=ON \
  -DGGML_NATIVE=ON \
  -DLLAMA_CURL=OFF \
  -DLLAMA_BUILD_UI=OFF \
  -DLLAMA_USE_PREBUILT_UI=OFF \
  -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH"

run_build cmake --build "$REPOS/llama.cpp/build-cuda" --config Release -j"$(nproc)"

release_root="$LOCAL_AI_HOME/llama-releases"
release="$release_root/$LLAMA_COMMIT"
temporary="${release}.install.$$"
[ ! -e "$release" ] || {
  echo "llama.cpp release already exists: $release" >&2
  exit 1
}
install -d -m 0555 "$release_root"
cmake --install "$REPOS/llama.cpp/build-cuda" --prefix "$temporary"
chown -R root:root "$temporary"
chmod -R go-w "$temporary"
mv "$temporary" "$release"
ln -sfn "$release" "$LOCAL_AI_HOME/llama-current.new"
mv -Tf "$LOCAL_AI_HOME/llama-current.new" "$LOCAL_AI_HOME/llama-current"
echo "[ok] llama.cpp CUDA build installed"
echo "[info] CUDA arch: $CUDA_ARCH"
