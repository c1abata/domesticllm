#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
for command in tmux flock nvidia-smi; do command -v "$command" >/dev/null || { echo "$command is required" >&2; exit 1; }; done
for binary in /opt/local-ai/current/bin/ds4-agent /opt/local-ai/llama-current/bin/llama-cli; do
  [ -x "$binary" ] || { echo "runtime missing: $binary" >&2; exit 1; }
done

systemctl disable --now domesticllm-lan-gateway.service domesticllm-llama-fast.service local-ai-ds4-native.service
install -o root -g root -m 0755 "$root/scripts/ds4-console" /usr/local/bin/ds4
find /srv/local-ai/models -maxdepth 1 -type f -name '*.gguf' -exec chmod 0444 {} +
rm -f \
  /srv/local-ai/models/ds4flash.gguf \
  /srv/local-ai/models/ds4flash-uncensored.gguf \
  /usr/local/bin/domesticllm-agent \
  /usr/local/bin/domesticllm-chat \
  /usr/local/bin/domesticllm-gateway \
  /usr/local/bin/domesticllm-query \
  /usr/local/bin/domesticllm-tui \
  /usr/local/bin/local-ai \
  /usr/local/sbin/domesticllm-agent-session \
  /usr/local/sbin/domesticllm-model \
  /usr/local/libexec/local-ai/domesticllm-gateway \
  /usr/local/libexec/local-ai/domesticllm-tui.py \
  /etc/systemd/system/domesticllm-lan-gateway.service \
  /etc/sudoers.d/domesticllm-agent \
  /etc/local-ai-gateway.key \
  /home/ale/.config/domesticllm/lan.key
systemctl daemon-reload
echo "installed unified local command: ds4"
