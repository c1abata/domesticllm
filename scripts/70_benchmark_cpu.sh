#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="${ENV_FILE:-/etc/local-ai.env}"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a
/opt/local-ai/bin/llama-bench -m "$LOCAL_AI_MODEL" -t "${LOCAL_AI_THREADS:-4}" -c "${LOCAL_AI_CTX:-4096}" -b "${LOCAL_AI_BATCH:-256}" -ub "${LOCAL_AI_UBATCH:-64}"
