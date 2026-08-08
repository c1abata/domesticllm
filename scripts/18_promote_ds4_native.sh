#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/ds4-runtime-lib.sh
. "$ROOT/scripts/ds4-runtime-lib.sh"

ENV_FILE="${DS4_ENV_FILE:-/etc/local-ai-ds4-runtime.env}"
GATE_FILE=""
CONFIRM=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --acceptance-file) GATE_FILE="${2:?missing acceptance file}"; shift 2 ;;
    --confirm) CONFIRM="${2:?missing confirmation}"; shift 2 ;;
    *) ds4_die "usage: $0 --acceptance-file FILE --confirm PROMOTE_DS4" ;;
  esac
done

ds4_require_root
[ "$CONFIRM" = PROMOTE_DS4 ] || ds4_die "explicit --confirm PROMOTE_DS4 is required"
[ -n "$GATE_FILE" ] || ds4_die "--acceptance-file is required"
ds4_require_gate_file "$GATE_FILE"

host="$(ds4_kv_get "$ENV_FILE" DS4_HOST)"
canary_port="$(ds4_kv_get "$ENV_FILE" DS4_CANARY_PORT)"
primary_port="$(ds4_kv_get "$ENV_FILE" DS4_PRIMARY_PORT)"
llama_unit="$(ds4_kv_get "$ENV_FILE" LLAMA_PRIMARY_UNIT)"
ds4_require_loopback "$host"
[ "$(ds4_kv_get "$ENV_FILE" DS4_PORT)" = "$canary_port" ] || ds4_die "DS4 is not configured as canary"
ds4_http_ready "$host" "$canary_port" || ds4_die "DS4 canary health gate failed"

systemctl stop local-ai-ds4-native.service
systemctl stop "$llama_unit"
ds4_set_env_key "$ENV_FILE" DS4_PORT "$primary_port"
systemctl start local-ai-ds4-native.service
if ! DS4_ENV_FILE="$ENV_FILE" "$ROOT/scripts/16_ds4_health.sh" wait; then
  ds4_info "promotion failed; restoring llama.cpp primary"
  systemctl stop local-ai-ds4-native.service || true
  ds4_set_env_key "$ENV_FILE" DS4_PORT "$canary_port"
  systemctl enable --now "$llama_unit"
  ds4_die "DS4 promotion health gate failed; llama.cpp restored"
fi
systemctl enable local-ai-ds4-native.service
systemctl disable "$llama_unit"

ds4_info "DS4 promoted to LAN bind 0.0.0.0 port $primary_port"
ds4_info "llama.cpp remains installed; use scripts/19_rollback_llama.sh if needed"
