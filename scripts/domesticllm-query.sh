#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Uso:
  domesticllm-query "domanda"
  printf '%s\n' "domanda" | domesticllm-query

Variabili opzionali:
  DOMESTICLLM_URL          endpoint OpenAI-compatible (default: loopback DS4)
  DOMESTICLLM_MODEL        modello richiesto (default: deepseek-v4-flash)
  DOMESTICLLM_MAX_TOKENS   token di completamento (default: 1024)
  DOMESTICLLM_TEMPERATURE  temperatura (default: 0)
  DOMESTICLLM_REASONING    direct, high o max (default: direct)
  DOMESTICLLM_SHOW_REASONING=1 mostra anche il ragionamento del modello
EOF
}

command -v curl >/dev/null || { echo "Errore: curl non installato" >&2; exit 1; }
command -v jq >/dev/null || { echo "Errore: jq non installato" >&2; exit 1; }

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac

if (($#)); then
  prompt="$*"
elif [ ! -t 0 ]; then
  prompt="$(cat)"
else
  usage >&2
  exit 2
fi
[ -n "$prompt" ] || { echo "Errore: prompt vuoto" >&2; exit 2; }

url="${DOMESTICLLM_URL:-http://127.0.0.1:8083/v1/chat/completions}"
model="${DOMESTICLLM_MODEL:-deepseek-v4-flash}"
max_tokens="${DOMESTICLLM_MAX_TOKENS:-1024}"
temperature="${DOMESTICLLM_TEMPERATURE:-0}"
reasoning="${DOMESTICLLM_REASONING:-direct}"
case "$max_tokens" in
  ''|*[!0-9]*|0) echo "Errore: DOMESTICLLM_MAX_TOKENS deve essere un intero positivo" >&2; exit 2 ;;
esac
if ! jq -en --argjson value "$temperature" '$value | numbers' >/dev/null 2>&1; then
  echo "Errore: DOMESTICLLM_TEMPERATURE deve essere un numero" >&2
  exit 2
fi
case "$reasoning" in
  direct|high|max) ;;
  *) echo "Errore: DOMESTICLLM_REASONING deve essere direct, high o max" >&2; exit 2 ;;
esac

request="$(mktemp)"
response="$(mktemp)"
trap 'rm -f "$request" "$response"' EXIT
jq -n --arg prompt "$prompt" --arg model "$model" \
  --arg reasoning "$reasoning" \
  --argjson max_tokens "$max_tokens" --argjson temperature "$temperature" \
  '{model:$model,messages:[{role:"user",content:$prompt}],max_tokens:$max_tokens,temperature:$temperature}
   + if $reasoning == "direct" then {thinking:{type:"disabled"}}
     else {reasoning_effort:$reasoning} end' \
  >"$request"

curl_args=(--fail-with-body --silent --show-error --connect-timeout 5 --data-binary "@$request"
  -H 'Content-Type: application/json' "$url")
validate_api_key() {
  case "$1" in
    *$'\n'*|*$'\r'*|*[!A-Za-z0-9._~+/=-]*)
      echo "Errore: API key con caratteri non supportati" >&2
      exit 2
      ;;
  esac
}
if [ -n "${LOCAL_AI_API_KEY_FILE:-}" ]; then
  [ -r "$LOCAL_AI_API_KEY_FILE" ] || { echo "Errore: file API key non leggibile" >&2; exit 2; }
  IFS= read -r api_key <"$LOCAL_AI_API_KEY_FILE"
  validate_api_key "$api_key"
  printf 'header = "Authorization: Bearer %s"\n' "$api_key" | curl --config - "${curl_args[@]}" >"$response"
elif [ -n "${LOCAL_AI_API_KEY:-}" ]; then
  validate_api_key "$LOCAL_AI_API_KEY"
  printf 'header = "Authorization: Bearer %s"\n' "$LOCAL_AI_API_KEY" | curl --config - "${curl_args[@]}" >"$response"
else
  curl "${curl_args[@]}" >"$response"
fi
finish_reason="$(jq -r '.choices[0].finish_reason // empty' "$response")"
if [ "$finish_reason" = length ]; then
  echo "Attenzione: risposta troncata dal limite token; aumentare DOMESTICLLM_MAX_TOKENS." >&2
  exit 3
fi

error="$(jq -r '.error.message // empty' "$response")"
[ -z "$error" ] || { echo "Errore modello: $error" >&2; exit 1; }
content="$(jq -r '.choices[0].message.content // empty' "$response")"
reasoning="$(jq -r '.choices[0].message.reasoning_content // .choices[0].message.reasoning // empty' "$response")"
if [ "${DOMESTICLLM_SHOW_REASONING:-0}" = 1 ] && [ -n "$reasoning" ]; then
  printf '%s\n\n' "$reasoning"
fi
if [ -n "$content" ]; then
  printf '%s\n' "$content"
elif [ -n "$reasoning" ]; then
  printf '%s\n' "$reasoning"
else
  echo "Errore: risposta priva di contenuto" >&2
  exit 1
fi
