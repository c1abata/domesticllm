#!/usr/bin/env bash
set -euo pipefail
umask 077

[ "$(id -u)" -ne 0 ] || { echo "run as the inference operator, not root" >&2; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="${MODEL_DIR:-/srv/local-ai/models}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CONFIG_DIR="$CONFIG_HOME/domesticllm"
UNIT_DIR="$CONFIG_HOME/systemd/user"

for command in install systemctl sha256sum python3; do
  command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 1; }
done
for model in DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf cognitivecomputations_Dolphin3.0-Mistral-24B-Q4_K_M.gguf Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf; do
  [ -r "$MODELS_DIR/$model" ] || { echo "missing model: $MODELS_DIR/$model" >&2; exit 1; }
done
expected="$(awk -F= '$1 == "MODEL_SHA256" {print $2}' "$ROOT/conf/ds4-runtime.lock")"
actual="$(sha256sum "$MODELS_DIR/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf" | awk '{print $1}')"
[ "$actual" = "$expected" ] || { echo "DeepSeek SHA-256 mismatch" >&2; exit 1; }

install -d -m 0700 "$CONFIG_DIR" "$UNIT_DIR" "$HOME/domesticllm/.runtime/ds4-kv"
if [ ! -e "$CONFIG_DIR/gateway.key" ]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(48))' >"$CONFIG_DIR/gateway.key"
fi
chmod 0600 "$CONFIG_DIR/gateway.key"
cat >"$CONFIG_DIR/ds4.env" <<EOF
DS4_MODEL=$MODELS_DIR/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf
DS4_HOST=0.0.0.0
DS4_PORT=8083
DS4_CONTEXT=100000
DS4_TOKENS=4096
DS4_THREADS=16
DS4_POWER=100
DS4_SSD_STREAMING_CACHE_EXPERTS=6GB
DS4_KV_DISK_DIR=$HOME/domesticllm/.runtime/ds4-kv
DS4_KV_DISK_SPACE_MB=8192
DS4_BATCHED_SESSIONS=1
CUDA_VISIBLE_DEVICES=0
EOF
cat >"$CONFIG_DIR/fast.env" <<EOF
FAST_HOST=0.0.0.0
FAST_PORT=8085
LOCAL_AI_MODEL=$MODELS_DIR/cognitivecomputations_Dolphin3.0-Mistral-24B-Q4_K_M.gguf
LOCAL_AI_MODEL_ALIAS=dolphin
LOCAL_AI_THREADS=16
LOCAL_AI_THREADS_BATCH=16
LOCAL_AI_CTX=16384
LOCAL_AI_PREDICT=4096
LOCAL_AI_BATCH=512
LOCAL_AI_UBATCH=128
LOCAL_AI_CACHE_TYPE_K=q8_0
LOCAL_AI_CACHE_TYPE_V=q8_0
EOF
for unit in domesticllm-ds4.service domesticllm-fast.service domesticllm-gateway.service; do
  install -m 0644 "$ROOT/systemd/user/$unit" "$UNIT_DIR/$unit"
done
systemctl --user daemon-reload
systemctl --user enable --now domesticllm-ds4.service domesticllm-fast.service domesticllm-gateway.service
echo "[ok] DomesticLLM user runtime active on 0.0.0.0:8080"
echo "[info] gateway key: $CONFIG_DIR/gateway.key"
echo "[info] fast profile: dolphin (edit $CONFIG_DIR/fast.env, then restart domesticllm-fast.service)"
