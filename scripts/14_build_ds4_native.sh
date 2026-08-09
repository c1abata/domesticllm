#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/ds4-runtime-lib.sh
. "$ROOT/scripts/ds4-runtime-lib.sh"

LOCK_FILE="${DS4_LOCK_FILE:-$ROOT/conf/ds4-runtime.lock}"
SOURCE=""
OUTPUT=""
JOBS="${JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '1')}"

usage() {
  cat <<'EOF'
Usage: scripts/14_build_ds4_native.sh --source CHECKOUT [--output DIR]

Builds the locked DS4 checkout offline as an unprivileged user. The checkout
must already exist, be clean, and be at the exact locked commit.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source) SOURCE="${2:?missing checkout}"; shift 2 ;;
    --output) OUTPUT="${2:?missing output directory}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) ds4_die "unknown option: $1" ;;
  esac
done

[ -n "$SOURCE" ] || ds4_die "--source is required"
ds4_require_non_root
for command in git make cc nvcc sha256sum install find sort xargs; do
  ds4_require_command "$command"
done

commit="$(ds4_kv_get "$LOCK_FILE" DS4_COMMIT)"
repo_url="$(ds4_kv_get "$LOCK_FILE" DS4_REPO_URL)"
arch="$(ds4_kv_get "$LOCK_FILE" DS4_CUDA_ARCH)"
target="$(ds4_kv_get "$LOCK_FILE" DS4_BUILD_TARGET)"
[ "$target" = cuda ] || ds4_die "unsupported locked build target: $target"
[ "$arch" = sm_86 ] || ds4_die "unexpected CUDA architecture: $arch"

SOURCE="$(cd "$SOURCE" && pwd -P)"
[ "$(git -C "$SOURCE" rev-parse HEAD)" = "$commit" ] || ds4_die "DS4 checkout is not at locked commit $commit"
[ -z "$(git -C "$SOURCE" status --porcelain)" ] || ds4_die "DS4 checkout is dirty"
origin="$(git -C "$SOURCE" remote get-url origin)"
case "$origin" in
  "$repo_url"|https://github.com/antirez/ds4|git@github.com:antirez/ds4.git) ;;
  *) ds4_die "unexpected DS4 origin: $origin" ;;
esac

if [ -z "$OUTPUT" ]; then
  OUTPUT="$ROOT/artifacts/ds4-$commit"
fi
[ ! -e "$OUTPUT" ] || ds4_die "output already exists: $OUTPUT"

export LC_ALL=C
export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH="$(git -C "$SOURCE" show -s --format=%ct HEAD)"

ds4_info "building DS4 $commit with make cuda CUDA_ARCH=$arch"
cflags="-O3 -ffast-math -g0 -march=znver3 -ffile-prefix-map=$SOURCE=. -Wall -Wextra -std=c99 -D_GNU_SOURCE -fno-finite-math-only"
nvccflags="-O3 -lineinfo --use_fast_math -arch=$arch -Xcompiler -march=znver3 -Xcompiler -pthread"
make -C "$SOURCE" clean
make -C "$SOURCE" -j"$JOBS" cuda CUDA_ARCH="$arch" \
  CFLAGS="$cflags" NVCCFLAGS="$nvccflags"
# Build the upstream test binaries, then run only model-independent tests here.
# Upstream `make test` defaults ds4_test to `--all`; when ds4flash.gguf exists
# that selects the resident-model CUDA path and can OOM on the domestic host.
# Model correctness is instead an explicit SSD-streaming hardware acceptance
# gate after artifact installation.
make -C "$SOURCE" -j"$JOBS" \
  ds4_test ds4_agent_test ds4-eval q4k-dot-test mxfp4-dot-test \
  tests/test_layer_pack tests/test_engine_mgpu_placement tests/test_gpu_args \
  tests/test_sampling CUDA_ARCH="$arch" CFLAGS="$cflags" NVCCFLAGS="$nvccflags"
(cd "$SOURCE" && ./ds4-eval --self-test-extractors)
(cd "$SOURCE" && ./ds4_agent_test)
(cd "$SOURCE" && ./ds4_test --server)
(cd "$SOURCE" && ./tests/test_layer_pack)
(cd "$SOURCE" && ./tests/test_engine_mgpu_placement)
(cd "$SOURCE" && ./tests/test_gpu_args)
(cd "$SOURCE" && ./tests/test_gpu_args_cli.sh)
(cd "$SOURCE" && ./tests/test_sampling)

for binary in ds4 ds4-server ds4-agent ds4-bench ds4-eval; do
  [ -x "$SOURCE/$binary" ] || ds4_die "build did not produce $binary"
done

install -d -m 0755 "$OUTPUT/bin"
for binary in ds4 ds4-server ds4-agent ds4-bench ds4-eval; do
  install -m 0755 "$SOURCE/$binary" "$OUTPUT/bin/$binary"
done
install -m 0644 "$SOURCE/LICENSE" "$OUTPUT/LICENSE"
cat >"$OUTPUT/build.env" <<EOF
BUILD_COMMIT=$commit
BUILD_REPO_URL=$repo_url
BUILD_TARGET=$target
BUILD_CUDA_ARCH=$arch
BUILD_SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH
BUILD_CC_VERSION=$(cc -dumpfullversion -dumpversion)
BUILD_CUDA_VERSION=$(nvcc --version | sed -n 's/.*release \([^,]*\).*/\1/p' | tail -n 1)
BUILD_NVCC=$(command -v nvcc)
EOF
(
  cd "$OUTPUT"
  find bin -type f -print | LC_ALL=C sort | xargs sha256sum
  sha256sum LICENSE build.env
) >"$OUTPUT/manifest.sha256"

ds4_info "verified build artifact: $OUTPUT"
