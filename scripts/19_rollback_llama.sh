#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/ds4-runtime-lib.sh
. "$ROOT/scripts/ds4-runtime-lib.sh"

ENV_FILE="${DS4_ENV_FILE:-/etc/local-ai-ds4-runtime.env}"
CONFIRM=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --confirm) CONFIRM="${2:?missing confirmation}"; shift 2 ;;
    *) ds4_die "usage: $0 --confirm ROLLBACK_LLAMA" ;;
  esac
done

ds4_require_root
[ "$CONFIRM" = ROLLBACK_LLAMA ] || ds4_die "explicit --confirm ROLLBACK_LLAMA is required"

host="$(ds4_kv_get "$ENV_FILE" DS4_HOST)"
canary_port="$(ds4_kv_get "$ENV_FILE" DS4_CANARY_PORT)"
primary_port="$(ds4_kv_get "$ENV_FILE" DS4_PRIMARY_PORT)"
llama_unit="$(ds4_kv_get "$ENV_FILE" LLAMA_PRIMARY_UNIT)"
ds4_require_loopback "$host"

systemctl disable --now local-ai-ds4-native.service
ds4_set_env_key "$ENV_FILE" DS4_PORT "$canary_port"
systemctl enable --now "$llama_unit"

for _ in $(seq 1 90); do
  if curl --fail --silent --show-error --max-time 10 \
    "http://${host}:${primary_port}/health" >/dev/null 2>&1; then
    ds4_info "llama.cpp rollback healthy on loopback port $primary_port"
    exit 0
  fi
  sleep 2
done
ds4_die "llama.cpp failed health after rollback; inspect $llama_unit"
