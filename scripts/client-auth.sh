#!/usr/bin/env bash

load_local_ai_key() {
  local key="${LOCAL_AI_API_KEY:-}"
  if [ -z "$key" ] && [ -n "${LOCAL_AI_API_KEY_FILE:-}" ] && [ -r "$LOCAL_AI_API_KEY_FILE" ]; then
    IFS= read -r key < "$LOCAL_AI_API_KEY_FILE"
  fi
  [ -n "$key" ] || {
    echo "Missing API key: set LOCAL_AI_API_KEY or a readable LOCAL_AI_API_KEY_FILE" >&2
    return 1
  }
  case "$key" in
    (*$'\n'*|*$'\r'*) echo "API key must not contain CR/LF" >&2; return 1 ;;
    (*[!A-Za-z0-9._~+/=-]*) echo "API key contains unsupported characters" >&2; return 1 ;;
  esac
  printf '%s' "$key"
}

curl_with_bearer() {
  local key="$1"
  shift
  printf 'header = "Authorization: Bearer %s"\n' "$key" | curl --config - "$@"
}
