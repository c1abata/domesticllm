#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="${ENV_FILE:-/etc/local-ai.env}"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=client-auth.sh
. "$ROOT/scripts/client-auth.sh"
PROMPT="${*:-}"
[ -n "$PROMPT" ] || { echo "Usage: $0 prompt"; exit 1; }
CLIENT_HOST="${LOCAL_AI_HOST:-127.0.0.1}"
case "$CLIENT_HOST" in
  0.0.0.0|::) CLIENT_HOST="127.0.0.1" ;;
esac
BASE="${LOCAL_AI_BASE_URL:-http://${CLIENT_HOST}:${LOCAL_AI_PORT:-8080}/v1}"
KEY="$(load_local_ai_key)"
MODEL="${LOCAL_AI_REQUEST_MODEL:-local-main}"
MAX_TOKENS="${LOCAL_AI_MAX_TOKENS:-512}"
TEMPERATURE="${LOCAL_AI_TEMPERATURE:-0.15}"
case "$MAX_TOKENS" in
  ''|*[!0-9]*|0) echo "LOCAL_AI_MAX_TOKENS must be a positive integer" >&2; exit 1 ;;
esac
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
jq -n --arg p "$PROMPT" --arg m "$MODEL" --argjson t "$TEMPERATURE" \
  --argjson n "$MAX_TOKENS" \
  '{model:$m,messages:[{role:"user",content:$p}],temperature:$t,max_tokens:$n}' > "$tmp"
curl_with_bearer "$KEY" --fail-with-body -sS "$BASE/chat/completions" -H "Content-Type: application/json" --data-binary @"$tmp" | jq -r '.choices[0].message.content // .error.message // .'
