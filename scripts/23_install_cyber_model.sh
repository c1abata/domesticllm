#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
staged=/srv/local-ai/downloads/Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf.partial
target=/srv/local-ai/models/Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf
expected_size=4920745984
expected_sha=73da18db1557e19e8ec2d6c1e8ef08e182c735d72f3bd526f6940f4fec96c1cb

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
[ -f "$staged" ] || { echo "verified staging model missing" >&2; exit 1; }
[ "$(stat -c %s "$staged")" = "$expected_size" ] || { echo "model size mismatch" >&2; exit 1; }
printf '%s  %s\n' "$expected_sha" "$staged" | sha256sum -c -
install -o root -g localai -m 0440 "$staged" "$target"
install -o root -g localai -m 0640 "$root/conf/llama-fast-cyber-uncensored.env" /usr/local/libexec/local-ai/conf/llama-fast-cyber-uncensored.env
install -o root -g root -m 0755 "$root/scripts/domesticllm-model" /usr/local/sbin/domesticllm-model
install -o root -g root -m 0755 "$root/scripts/domesticllm-tui.py" /usr/local/libexec/local-ai/domesticllm-tui.py
install -o root -g root -m 0755 "$root/scripts/domesticllm-gateway.py" /usr/local/libexec/local-ai/domesticllm-gateway
install -o root -g root -m 0644 "$root/systemd/domesticllm-lan-gateway.service" /etc/systemd/system/domesticllm-lan-gateway.service
systemctl daemon-reload
systemctl restart domesticllm-lan-gateway.service
systemctl is-active --quiet domesticllm-lan-gateway.service
echo "cyber model installed but not activated"
