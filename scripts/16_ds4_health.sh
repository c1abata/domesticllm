#!/usr/bin/env bash
set -euo pipefail

if [ -r /usr/local/libexec/local-ai/scripts/ds4-runtime-lib.sh ]; then
  LIB=/usr/local/libexec/local-ai/scripts/ds4-runtime-lib.sh
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  LIB="$ROOT/scripts/ds4-runtime-lib.sh"
fi
# shellcheck source=scripts/ds4-runtime-lib.sh
. "$LIB"

ENV_FILE="${DS4_ENV_FILE:-/etc/local-ai-ds4-runtime.env}"
MODE="${1:-health}"

load_runtime() {
  host="$(ds4_kv_get "$ENV_FILE" DS4_HOST)"
  port="$(ds4_kv_get "$ENV_FILE" DS4_PORT)"
  model="$(ds4_kv_get "$ENV_FILE" DS4_MODEL)"
  model_sha="$(ds4_kv_get "$ENV_FILE" DS4_MODEL_SHA256)"
  current="$(ds4_kv_get "$ENV_FILE" DS4_CURRENT)"
  releases="$(ds4_kv_get "$ENV_FILE" DS4_RELEASES_DIR)"
  ds4_require_loopback "$host"
}

preflight() {
  local resolved
  [ -L "$current" ] || ds4_die "current release is not a symlink: $current"
  resolved="$(readlink -f "$current")"
  case "$resolved" in
    "$releases"/*) ;;
    *) ds4_die "current release escapes release root: $resolved" ;;
  esac
  [ -x "$current/bin/ds4-server" ] || ds4_die "ds4-server is not executable"
  [ -z "$(find "$resolved/bin" -type f -perm /022 -print -quit)" ] || ds4_die "release binaries are writable by group/other"
  ds4_reject_partial_model "$model"
  [ -z "$(find "$model" -perm /022 -print -quit)" ] || ds4_die "model is writable by group/other"
  ds4_verify_sha256 "$model" "$model_sha"

  runtime_mode="$(ds4_kv_get "$ENV_FILE" DS4_RUNTIME_MODE)"
  [ "$runtime_mode" = "ssd-streaming" ] || ds4_die "unsupported DS4_RUNTIME_MODE: $runtime_mode"
  cache_experts="$(ds4_kv_get "$ENV_FILE" DS4_SSD_STREAMING_CACHE_EXPERTS)"
  case "$cache_experts" in
    *GB) [ "${cache_experts%GB}" -gt 0 ] 2>/dev/null || ds4_die "invalid SSD streaming cache: $cache_experts" ;;
    *) ds4_die "DS4_SSD_STREAMING_CACHE_EXPERTS must use a positive GB value" ;;
  esac
  min_vram_mib="$(ds4_kv_get "$ENV_FILE" DS4_MIN_DEVICE_VRAM_MIB)"
  case "$min_vram_mib" in
    ''|*[!0-9]*) ds4_die "DS4_MIN_DEVICE_VRAM_MIB must be an integer" ;;
  esac
  ds4_require_command nvidia-smi
  visible_devices="$(ds4_kv_get "$ENV_FILE" CUDA_VISIBLE_DEVICES)"
  [ -n "$visible_devices" ] || ds4_die "CUDA_VISIBLE_DEVICES must select explicit GPU indexes"
  selected_devices=0
  smallest_vram_mib="$(nvidia-smi --query-gpu=index,memory.total --format=csv,noheader,nounits |
    awk -F, -v visible="$visible_devices" '
      BEGIN {
        n = split(visible, ids, ",")
        for (i = 1; i <= n; i++) {
          gsub(/ /, "", ids[i])
          wanted[ids[i]] = 1
        }
      }
      {
        idx = $1
        mem = $2
        gsub(/ /, "", idx)
        gsub(/ /, "", mem)
        if (wanted[idx]) {
          count++
          if (smallest == 0 || mem < smallest) smallest = mem
        }
      }
      END { print smallest + 0, count + 0 }
    ')"
  selected_devices="${smallest_vram_mib#* }"
  smallest_vram_mib="${smallest_vram_mib%% *}"
  [ "$selected_devices" -gt 0 ] || ds4_die "none of CUDA_VISIBLE_DEVICES were found"
  [ "$smallest_vram_mib" -ge "$min_vram_mib" ] || ds4_die \
    "DS4 SSD streaming needs ${min_vram_mib} MiB on every selected GPU; smallest has ${smallest_vram_mib} MiB"
}

case "$MODE" in
  preflight)
    load_runtime
    preflight
    ;;
  health)
    load_runtime
    ds4_http_ready "$host" "$port" || ds4_die "DS4 API is not ready at ${host}:${port}"
    ;;
  wait)
    load_runtime
    attempts="$(ds4_kv_get "$ENV_FILE" DS4_HEALTH_ATTEMPTS)"
    interval="$(ds4_kv_get "$ENV_FILE" DS4_HEALTH_INTERVAL)"
    case "$attempts:$interval" in
      *[!0-9:]*|0:*|*:0) ds4_die "invalid health retry configuration" ;;
    esac
    for ((i = 1; i <= attempts; i++)); do
      if ds4_http_ready "$host" "$port"; then
        ds4_info "DS4 API ready at ${host}:${port}"
        exit 0
      fi
      sleep "$interval"
    done
    ds4_die "DS4 API did not become ready after $((attempts * interval)) seconds"
    ;;
  doctor)
    failures=0
    printf 'DS4 doctor\n'
    if [ -r /etc/os-release ] && grep -q '^ID=ubuntu$' /etc/os-release; then
      printf '[ok] Ubuntu host\n'
    else
      printf '[fail] Ubuntu host required\n' >&2
      failures=$((failures + 1))
    fi
    ram_gib="$(awk '/MemTotal/ {print int($2/1024/1024)}' /proc/meminfo 2>/dev/null || printf '0')"
    if [ "$ram_gib" -ge 112 ]; then
      printf '[ok] RAM: %s GiB\n' "$ram_gib"
    else
      printf '[fail] RAM: %s GiB; minimum 112 GiB\n' "$ram_gib" >&2
      failures=$((failures + 1))
    fi
    if command -v nvcc >/dev/null 2>&1; then
      printf '[ok] nvcc available\n'
    else
      printf '[fail] nvcc unavailable; validate CUDA manually\n' >&2
      failures=$((failures + 1))
    fi
    if command -v nvidia-smi >/dev/null 2>&1; then
      gpu_count="$(nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | wc -l)"
      if [ "$gpu_count" -ge 2 ]; then
        printf '[ok] visible GPUs: %s\n' "$gpu_count"
      else
        printf '[fail] visible GPUs: %s; target requires two\n' "$gpu_count" >&2
        failures=$((failures + 1))
      fi
      nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader || true
      nvidia-smi topo -m || true
    else
      printf '[fail] nvidia-smi unavailable\n' >&2
      failures=$((failures + 1))
    fi
    if [ -r "$ENV_FILE" ] && (load_runtime && preflight); then
      printf '[ok] locked release, permissions and model checksum\n'
    else
      printf '[fail] release/model preflight\n' >&2
      failures=$((failures + 1))
    fi
    [ "$failures" -eq 0 ] || ds4_die "doctor found $failures hard failure(s)"
    ;;
  *) ds4_die "usage: $0 [preflight|health|wait|doctor]" ;;
esac
