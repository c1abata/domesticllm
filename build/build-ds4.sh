#!/usr/bin/env bash
set -euo pipefail
[ "${PDS4_OFFLINE:-0}" = 1 ] || { echo "PDS4_OFFLINE=1 is required" >&2; exit 1; }
[ "$#" -eq 2 ] || { echo "usage: build-ds4.sh SOURCE OUTPUT" >&2; exit 2; }
source_dir="$(readlink -f "$1")"
output_dir="$2"
[ -d "$source_dir/.git" ] || { echo "DS4 source is not a Git checkout" >&2; exit 1; }
expected=80df56af4070d0fc62f6f9682b1854f8e5be8b00
[ "$(git -C "$source_dir" rev-parse HEAD)" = "$expected" ] || { echo "wrong DS4 commit" >&2; exit 1; }
cmake -S "$source_dir" -B "$output_dir" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86
cmake --build "$output_dir" --parallel "${JOBS:-1}"
