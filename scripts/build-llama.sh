#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source_dir=${LLAMA_CPP_SOURCE_DIR:-"$project_dir/vendor/llama.cpp"}
build_dir=${LLAMA_CPP_BUILD_DIR:-"$project_dir/build/llama.cpp"}
cpu_target=${CPU_TARGET:-native}

if [[ ! -f "$source_dir/CMakeLists.txt" ]]; then
  printf 'llama.cpp source not found: %s\n' "$source_dir" >&2
  printf 'Place a reviewed local checkout there or set LLAMA_CPP_SOURCE_DIR.\n' >&2
  exit 2
fi

cmake_args=(
  -S "$source_dir"
  -B "$build_dir"
  -DCMAKE_BUILD_TYPE=Release
  -DGGML_NATIVE="$([[ "$cpu_target" == native ]] && printf ON || printf OFF)"
  -DGGML_BLAS=ON
  -DGGML_BLAS_VENDOR=OpenBLAS
  -DGGML_CUDA=OFF
)

if [[ "$cpu_target" != native ]]; then
  cmake_args+=("-DCMAKE_C_FLAGS=-march=$cpu_target" "-DCMAKE_CXX_FLAGS=-march=$cpu_target")
fi

cmake "${cmake_args[@]}"
cmake --build "$build_dir" --config Release --parallel

if [[ ! -x "$build_dir/bin/llama-server" ]]; then
  printf 'build completed but llama-server is missing: %s\n' "$build_dir/bin/llama-server" >&2
  exit 3
fi

printf 'Built %s\n' "$build_dir/bin/llama-server"
