#!/usr/bin/env bash
set -euo pipefail
[ "${PDS4_OFFLINE:-0}" = 1 ] || { echo "PDS4_OFFLINE=1 is required" >&2; exit 1; }
[ "$#" -eq 2 ] || { echo "usage: build-ds4.sh SOURCE OUTPUT" >&2; exit 2; }
source_dir="$(readlink -f "$1")"
output_dir="$(readlink -m "$2")"
[ -d "$source_dir/.git" ] || { echo "DS4 source is not a Git checkout" >&2; exit 1; }
expected=80df56af4070d0fc62f6f9682b1854f8e5be8b00
[ "$(git -C "$source_dir" rev-parse HEAD)" = "$expected" ] || { echo "wrong DS4 commit" >&2; exit 1; }
[ -z "$(git -C "$source_dir" status --porcelain)" ] || { echo "DS4 source checkout is dirty" >&2; exit 1; }
[ ! -e "$output_dir" ] || { echo "output already exists: $output_dir" >&2; exit 1; }
for command in make cc nvcc install sha256sum; do
  command -v "$command" >/dev/null || { echo "missing build command: $command" >&2; exit 1; }
done

jobs="${JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '1')}"
temporary="${output_dir}.install.$$"
cleanup() { rm -rf -- "$temporary"; }
trap cleanup EXIT
export LC_ALL=C
export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH="$(git -C "$source_dir" show -s --format=%ct HEAD)"
cflags="-O3 -ffast-math -g0 -march=znver3 -ffile-prefix-map=$source_dir=. -Wall -Wextra -std=c99 -D_GNU_SOURCE -fno-finite-math-only"
nvccflags="-O3 -lineinfo --use_fast_math -arch=sm_86 -Xcompiler -march=znver3 -Xcompiler -pthread"

make -C "$source_dir" clean
make -C "$source_dir" -j"$jobs" cuda CUDA_ARCH=sm_86 CFLAGS="$cflags" NVCCFLAGS="$nvccflags"
make -C "$source_dir" -j"$jobs" \
  ds4_test ds4_agent_test ds4-eval q4k-dot-test mxfp4-dot-test \
  tests/test_layer_pack tests/test_engine_mgpu_placement tests/test_gpu_args \
  tests/test_sampling CUDA_ARCH=sm_86 CFLAGS="$cflags" NVCCFLAGS="$nvccflags"
(cd "$source_dir" && ./ds4-eval --self-test-extractors)
(cd "$source_dir" && ./ds4_agent_test)
(cd "$source_dir" && ./ds4_test --server)
(cd "$source_dir" && ./tests/test_layer_pack)
(cd "$source_dir" && ./tests/test_engine_mgpu_placement)
(cd "$source_dir" && ./tests/test_gpu_args)
(cd "$source_dir" && ./tests/test_gpu_args_cli.sh)
(cd "$source_dir" && ./tests/test_sampling)

install -d -m 0755 "$temporary/bin"
for binary in ds4 ds4-server ds4-agent ds4-bench ds4-eval; do
  install -m 0755 "$source_dir/$binary" "$temporary/bin/$binary"
done
install -m 0644 "$source_dir/LICENSE" "$temporary/LICENSE"
cc_version="$(cc -dumpfullversion -dumpversion)"
cuda_version="$(nvcc --version | sed -n 's/.*release \([^,]*\).*/\1/p' | tail -n 1)"
nvcc_path="$(command -v nvcc)"
{
  printf 'BUILD_COMMIT=%s\n' "$expected"
  printf 'BUILD_TARGET=cuda\nBUILD_CUDA_ARCH=sm_86\n'
  printf 'BUILD_SOURCE_DATE_EPOCH=%s\n' "$SOURCE_DATE_EPOCH"
  printf 'BUILD_CC_VERSION=%s\n' "$cc_version"
  printf 'BUILD_CUDA_VERSION=%s\n' "$cuda_version"
  printf 'BUILD_NVCC=%s\n' "$nvcc_path"
} >"$temporary/build.env"
(
  cd "$temporary"
  find bin -type f -print | LC_ALL=C sort | xargs sha256sum
  sha256sum LICENSE build.env
) >"$temporary/manifest.sha256"
mv "$temporary" "$output_dir"
trap - EXIT
