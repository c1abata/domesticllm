#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
config_file=${CPU_INFERENCE_CONFIG:-"$project_dir/config/cpu-inference.env"}
server_bin=${LLAMA_SERVER_BIN:-"$project_dir/build/llama.cpp/bin/llama-server"}

if [[ ! -r "$config_file" ]]; then
  printf 'missing configuration: %s\nCopy config/cpu-inference.env.example first.\n' "$config_file" >&2
  exit 2
fi

# The configuration is operator-maintained shell assignments only.
# shellcheck disable=SC1090
source "$config_file"

: "${MODEL:?MODEL is required}"
: "${MODEL_SHA256:?MODEL_SHA256 is required}"
: "${HOST:?HOST is required}"
: "${PORT:?PORT is required}"
: "${CTX_SIZE:?CTX_SIZE is required}"
: "${THREADS:?THREADS is required}"
: "${PARALLEL:?PARALLEL is required}"

[[ -x "$server_bin" ]] || { printf 'llama-server not executable: %s\n' "$server_bin" >&2; exit 3; }
[[ -r "$MODEL" ]] || { printf 'model not readable: %s\n' "$MODEL" >&2; exit 4; }
[[ "$HOST" == 127.0.0.1 || "$HOST" == ::1 ]] || { printf 'refusing non-loopback host: %s\n' "$HOST" >&2; exit 5; }

actual_sha=$(sha256sum "$MODEL" | awk '{print $1}')
[[ "$actual_sha" == "$MODEL_SHA256" ]] || {
  printf 'model checksum mismatch\nexpected: %s\nactual:   %s\n' "$MODEL_SHA256" "$actual_sha" >&2
  exit 6
}

printf 'starting llama-server model=%s sha256=%s ctx=%s threads=%s parallel=%s host=%s port=%s\n' \
  "$MODEL" "$actual_sha" "$CTX_SIZE" "$THREADS" "$PARALLEL" "$HOST" "$PORT"

args=(
  --model "$MODEL"
  --host "$HOST"
  --port "$PORT"
  --ctx-size "$CTX_SIZE"
  --threads "$THREADS"
  --parallel "$PARALLEL"
)

if [[ -n "${EXTRA_ARGS:-}" ]]; then
  read -r -a extra_args <<<"$EXTRA_ARGS"
  args+=("${extra_args[@]}")
fi

exec "$server_bin" "${args[@]}"
