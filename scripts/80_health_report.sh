#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="${ENV_FILE:-/etc/local-ai.env}"
SERVICE="${SERVICE:-local-ai-cpu}"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a
PORT="${LOCAL_AI_PORT:-8080}"
CLIENT_HOST="${LOCAL_AI_HOST:-127.0.0.1}"
case "$CLIENT_HOST" in
  0.0.0.0|::) CLIENT_HOST="127.0.0.1" ;;
esac
SLOT_DIR="${LOCAL_AI_SLOT_SAVE_PATH:-/var/cache/local-ai/slots}"
echo "== service =="
systemctl is-active "$SERVICE" || true
echo "== health =="
curl -s "http://${CLIENT_HOST}:${PORT}/health" || true
echo
echo "== memory =="
free -h
echo "== sockets =="
ss -lntp | grep ":${PORT}" || true
echo "== cache dir =="
du -h "$SLOT_DIR" 2>/dev/null || true
