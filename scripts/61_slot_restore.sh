#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="${ENV_FILE:-/etc/local-ai.env}"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/scripts/client-auth.sh"
SLOT="${1:-0}"
FILE="${2:-slot-${SLOT}.bin}"
BASE="${LOCAL_AI_BASE_URL_RAW:-http://${LOCAL_AI_HOST:-127.0.0.1}:${LOCAL_AI_PORT:-8080}}"
KEY="$(load_local_ai_key)"
curl_with_bearer "$KEY" --fail-with-body -sS -X POST "$BASE/slots/${SLOT}?action=restore" -H "Content-Type: application/json" -d "{\"filename\":\"$FILE\"}" | jq .
