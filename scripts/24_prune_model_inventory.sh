#!/usr/bin/env bash
set -euo pipefail

required=(
  /srv/local-ai/models/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf
  /srv/local-ai/models/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf
  /srv/local-ai/models/mistralai_Mistral-Small-3.1-24B-Instruct-2503-Q4_K_M.gguf
  /srv/local-ai/models/cognitivecomputations_Dolphin3.0-Mistral-24B-Q4_K_M.gguf
  /srv/local-ai/models/Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf
)
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
for model in "${required[@]}"; do
  [ -f "$model" ] || { echo "refusing prune; required model missing: $model" >&2; exit 1; }
done

rm -f \
  /srv/local-ai/models/Huihui-DeepSeek-V4-Flash-BF16-abliterated-ds4-Q2.gguf \
  /srv/local-ai/models/Qwen3.5-9B-Uncensored-cyber-v3.Q4_K_M.gguf \
  /srv/local-ai/models/Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M.gguf \
  /srv/local-ai/downloads/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf.partial \
  /srv/local-ai/downloads/dolphin3-mistral-24b-q4_k_m.gguf.partial \
  /srv/local-ai/downloads/mistral-small-3.1-24b-q4_k_m.gguf.partial \
  /srv/local-ai/downloads/Qwen3.5-9B-Uncensored-cyber-v3.Q4_K_M.gguf.partial \
  /srv/local-ai/downloads/Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M.gguf.partial \
  /srv/local-ai/downloads/Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf.partial \
  /srv/local-ai/downloads/qwen-download.log \
  /srv/local-ai/downloads/cyber-download.log \
  /srv/local-ai/downloads/qwythos-download.log \
  /srv/local-ai/downloads/dolphin-cyber-download.log
echo "model inventory pruned to the approved allowlist"
