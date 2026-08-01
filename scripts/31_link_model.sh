#!/usr/bin/env bash
set -euo pipefail
MODEL="${1:?Usage: $0 /opt/local-ai/models/model.gguf}"
[ -f "$MODEL" ] || { echo "Model not found: $MODEL"; exit 1; }
ln -sfn "$MODEL" /opt/local-ai/models/main.gguf
chown -h localai:localai /opt/local-ai/models/main.gguf
echo "[ok] /opt/local-ai/models/main.gguf -> $MODEL"
