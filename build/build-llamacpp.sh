#!/usr/bin/env bash
set -euo pipefail
[ "${PDS4_OFFLINE:-0}" = 1 ] || { echo "PDS4_OFFLINE=1 is required" >&2; exit 1; }
[ "$#" -eq 2 ] || { echo "usage: build-llamacpp.sh SOURCE OUTPUT" >&2; exit 2; }
source_dir="$(readlink -f "$1")"
output_dir="$2"
[ -d "$source_dir/.git" ] || { echo "llama.cpp source is not a Git checkout" >&2; exit 1; }
expected=876a4321163249c43ca4e986818fab5ab081f282
[ "$(git -C "$source_dir" rev-parse HEAD)" = "$expected" ] || { echo "wrong llama.cpp commit" >&2; exit 1; }
cmake -S "$source_dir" -B "$output_dir" \
  -DGGML_CUDA=ON -DGGML_NATIVE=OFF -DLLAMA_CURL=OFF \
  -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86
cmake --build "$output_dir" --parallel "${JOBS:-1}"
