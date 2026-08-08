#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/ds4-runtime-lib.sh
. "$ROOT/scripts/ds4-runtime-lib.sh"

fail() { printf 'not ok - %s\n' "$*" >&2; exit 1; }
ok() { printf 'ok - %s\n' "$*"; }

lock="$ROOT/conf/ds4-runtime.lock"
env_file="$ROOT/conf/ds4-runtime-a4500.env"
[ "$(ds4_kv_get "$lock" DS4_BRANCH)" = ds4f-mxfp4 ] || fail "DS4 branch pin"
[ "$(ds4_kv_get "$lock" DS4_COMMIT)" = 80df56af4070d0fc62f6f9682b1854f8e5be8b00 ] || fail "DS4 commit pin"
[ "$(ds4_kv_get "$lock" DS4_BUILD_TARGET)" = cuda ] || fail "CUDA build target"
[ "$(ds4_kv_get "$lock" DS4_CUDA_ARCH)" = sm_86 ] || fail "sm_86 architecture"
[ "$(ds4_kv_get "$lock" DS4_MXFP4_CUDA_SUPPORTED)" = 0 ] || fail "MXFP4 CUDA capability gate"
[ "$(ds4_kv_get "$lock" MODEL_SHA256)" = "$(ds4_kv_get "$env_file" DS4_MODEL_SHA256)" ] || fail "model lock/profile drift"
ok "immutable DS4 build inputs"

[ "$(ds4_kv_get "$env_file" DS4_HOST)" = 0.0.0.0 ] || fail "LAN bind"
[ "$(ds4_kv_get "$env_file" DS4_PORT)" = 8083 ] || fail "canary port"
[ "$(ds4_kv_get "$env_file" DS4_PRIMARY_PORT)" = 8082 ] || fail "primary port"
[ "$(ds4_kv_get "$env_file" DS4_FALLBACK_PORT)" = 8084 ] || fail "fallback port"
[ "$(ds4_kv_get "$env_file" DS4_CONTEXT)" = 100000 ] || fail "100k context"
[ "$(ds4_kv_get "$env_file" DS4_KV_DISK_SPACE_MB)" = 8192 ] || fail "8 GiB KV budget"
[ "$(ds4_kv_get "$env_file" DS4_POWER)" = 100 ] || fail "measured domestic power profile"
[ "$(ds4_kv_get "$env_file" DS4_BATCHED_SESSIONS)" = 1 ] || fail "validated resident-session count"
[ "$(ds4_kv_get "$env_file" DS4_RUNTIME_MODE)" = ssd-streaming ] || fail "SSD streaming mode"
[ "$(ds4_kv_get "$env_file" DS4_SSD_STREAMING_CACHE_EXPERTS)" = 6GB ] || fail "working-set-safe expert cache budget"
[ "$(ds4_kv_get "$env_file" DS4_MIN_DEVICE_VRAM_MIB)" = 16000 ] || fail "per-device VRAM gate"
[ "$(ds4_kv_get "$env_file" CUDA_VISIBLE_DEVICES)" = 0 ] || fail "exclusive DS4 GPU"
ok "A4500 runtime profile"

grep -Fq 'make -C "$SOURCE" -j"$JOBS" cuda CUDA_ARCH="$arch"' "$ROOT/scripts/14_build_ds4_native.sh" || fail "explicit CUDA target"
grep -Fq 'mxfp4-dot-test' "$ROOT/scripts/14_build_ds4_native.sh" || fail "MXFP4 scalar regression gate"
grep -Fq './ds4_test --server' "$ROOT/scripts/14_build_ds4_native.sh" || fail "model-independent upstream unit gate"
! grep -Fq 'make -C "$SOURCE" -j"$JOBS" test ' "$ROOT/scripts/14_build_ds4_native.sh" || fail "resident all-tests path enabled during build"
grep -Fq 'ds4_require_non_root' "$ROOT/scripts/14_build_ds4_native.sh" || fail "non-root build guard"
! grep -Eq 'git (clone|pull)|curl|wget|apt(-get)? ' "$ROOT/scripts/14_build_ds4_native.sh" || fail "implicit build network"
ok "offline non-root build"

grep -Fq 'chown root:root "$home" "$model_dir"' "$ROOT/scripts/15_install_ds4_native.sh" || fail "immutable install roots"
grep -Fq '/usr/local/libexec/local-ai/scripts' "$ROOT/scripts/15_install_ds4_native.sh" || fail "installed helper layout"
ok "installed release and helper ownership"

native_unit="$ROOT/systemd/local-ai-ds4-native.service"
grep -Fq 'NoNewPrivileges=yes' "$native_unit" || fail "NoNewPrivileges"
grep -Fq 'ProtectSystem=strict' "$native_unit" || fail "ProtectSystem"
grep -Fq -- '--host ${DS4_HOST}' "$native_unit" || fail "configured bind"
grep -Fq 'ExecStartPost=/usr/local/libexec/local-ai/ds4-health wait' "$native_unit" || fail "health gate"
ok "systemd hardening and health gate"

tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/releases/test/bin"
printf '#!/bin/sh\nexit 0\n' >"$tmp/releases/test/bin/ds4-server"
chmod 0555 "$tmp/releases/test/bin/ds4-server"
printf 'verified model fixture\n' >"$tmp/model.gguf"
chmod 0440 "$tmp/model.gguf"
ln -s "$tmp/releases/test" "$tmp/current"
fixture_sha="$(sha256sum "$tmp/model.gguf" | awk '{print $1}')"
cat >"$tmp/runtime.env" <<EOF
DS4_HOST=127.0.0.1
DS4_PORT=8083
DS4_MODEL=$tmp/model.gguf
DS4_MODEL_SHA256=$fixture_sha
DS4_CURRENT=$tmp/current
DS4_RELEASES_DIR=$tmp/releases
DS4_RUNTIME_MODE=ssd-streaming
DS4_SSD_STREAMING_CACHE_EXPERTS=1GB
DS4_MIN_DEVICE_VRAM_MIB=1
CUDA_VISIBLE_DEVICES=0,1
EOF
mkdir -p "$tmp/bin"
cat >"$tmp/bin/nvidia-smi" <<'EOF'
#!/bin/sh
printf '0, 20480\n1, 20480\n2, 100000\n'
EOF
chmod 0755 "$tmp/bin/nvidia-smi"
PATH="$tmp/bin:$PATH" DS4_ENV_FILE="$tmp/runtime.env" "$ROOT/scripts/16_ds4_health.sh" preflight || fail "valid preflight"
sed "s/DS4_MODEL_SHA256=.*/DS4_MODEL_SHA256=$(printf '0%.0s' {1..64})/" \
  "$tmp/runtime.env" >"$tmp/runtime-bad.env"
if PATH="$tmp/bin:$PATH" DS4_ENV_FILE="$tmp/runtime-bad.env" "$ROOT/scripts/16_ds4_health.sh" preflight >/dev/null 2>&1; then
  fail "wrong model hash accepted"
fi
ok "model hash rejection"

sed 's/DS4_MIN_DEVICE_VRAM_MIB=1/DS4_MIN_DEVICE_VRAM_MIB=50000/' \
  "$tmp/runtime.env" >"$tmp/runtime-vram.env"
if PATH="$tmp/bin:$PATH" DS4_ENV_FILE="$tmp/runtime-vram.env" "$ROOT/scripts/16_ds4_health.sh" preflight >/dev/null 2>&1; then
  fail "insufficient native VRAM accepted"
fi
ok "native VRAM capacity rejection"

cat >"$tmp/acceptance.env" <<'EOF'
CORRECTNESS=pass
TOOL_CALLING=pass
DECODE_NOT_BELOW_BASELINE=pass
TTFT_WITHIN_10_PERCENT=pass
GPU_ISOLATION=pass
STRESS_4H=pass
ROLLBACK_TESTED=pass
EOF
chmod 0600 "$tmp/acceptance.env"
ds4_require_gate_file "$tmp/acceptance.env" || fail "valid acceptance gates"
sed 's/GPU_ISOLATION=pass/GPU_ISOLATION=fail/' "$tmp/acceptance.env" >"$tmp/acceptance-bad.env"
chmod 0600 "$tmp/acceptance-bad.env"
if (ds4_require_gate_file "$tmp/acceptance-bad.env") >/dev/null 2>&1; then
  fail "failed acceptance gate accepted"
fi
ok "promotion acceptance gates"

for script in "$ROOT"/scripts/{14_build_ds4_native,15_install_ds4_native,16_ds4_health,17_benchmark_ds4_acceptance,18_promote_ds4_native,19_rollback_llama}.sh; do
  bash -n "$script" || fail "syntax: $script"
done
ok "runtime script syntax"
