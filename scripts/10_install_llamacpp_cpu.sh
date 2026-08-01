#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=vendor-lib.sh
. "$ROOT/scripts/vendor-lib.sh"
prepare_build_dirs
checkout_locked_repo llama.cpp "$LLAMA_REPO_URL" "$LLAMA_COMMIT"
run_build cmake -S "$REPOS/llama.cpp" -B "$REPOS/llama.cpp/build" -DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS -DGGML_NATIVE=ON
run_build cmake --build "$REPOS/llama.cpp/build" --config Release -j"$(nproc)"
install -m 0755 "$REPOS/llama.cpp/build/bin/llama-server" "$LOCAL_AI_HOME/bin/llama-server"
[ ! -x "$REPOS/llama.cpp/build/bin/llama-cli" ] || install -m 0755 "$REPOS/llama.cpp/build/bin/llama-cli" "$LOCAL_AI_HOME/bin/llama-cli"
[ ! -x "$REPOS/llama.cpp/build/bin/llama-bench" ] || install -m 0755 "$REPOS/llama.cpp/build/bin/llama-bench" "$LOCAL_AI_HOME/bin/llama-bench"
echo "[ok] llama.cpp CPU build installed"
