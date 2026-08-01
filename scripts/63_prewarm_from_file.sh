#!/usr/bin/env bash
set -euo pipefail
FILE="${1:?Usage: $0 context.md cache-name.bin}"
CACHE="${2:?Usage: $0 context.md cache-name.bin}"
PROMPT="$(cat "$FILE")

Memorizza questo contesto per la sessione. Rispondi solo: CONTEXT_READY."
bash "$(dirname "$0")/50_ask.sh" "$PROMPT"
bash "$(dirname "$0")/60_slot_save.sh" 0 "$CACHE"
