#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
command -v visudo >/dev/null || { echo "visudo is required" >&2; exit 1; }
command -v tmux >/dev/null || { echo "tmux is required" >&2; exit 1; }
model=/opt/local-ai/models/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf
[ -f "$model" ] || { echo "locked DS4 model missing: $model" >&2; exit 1; }
visudo -cf "$root/conf/sudoers-domesticllm-agent" >/dev/null
install -o root -g root -m 0755 "$root/scripts/domesticllm-agent-session" /usr/local/sbin/domesticllm-agent-session
install -o root -g root -m 0755 "$root/scripts/domesticllm-agent" /usr/local/bin/domesticllm-agent
install -o root -g root -m 0440 "$root/conf/sudoers-domesticllm-agent" /etc/sudoers.d/domesticllm-agent
chmod 0444 "$model"
visudo -c >/dev/null
systemctl start domesticllm-lan-gateway.service
echo "native DS4 agent installed"
