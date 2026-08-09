#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
config_file="$project_dir/config/llmm.env"
source_dir=/srv/local-ai/build/llama.cpp-876a4321163249c43ca4e986818fab5ab081f282
key_file=/home/ale/.config/cpu-inference/api-keys

[[ -r "$config_file" ]] || { printf 'missing deployment configuration: %s\n' "$config_file" >&2; exit 2; }
[[ -f "$source_dir/CMakeLists.txt" ]] || { printf 'llama.cpp source missing: %s\n' "$source_dir" >&2; exit 3; }

# shellcheck disable=SC1090
source "$config_file"
[[ "$HOST" == 0.0.0.0 ]] || { printf 'llmm deployment requires HOST=0.0.0.0\n' >&2; exit 4; }
[[ "$GPU_LAYERS" == 0 ]] || { printf 'llmm deployment requires GPU_LAYERS=0\n' >&2; exit 5; }
[[ "$API_KEY_FILE" == "$key_file" ]] || { printf 'unexpected API key path: %s\n' "$API_KEY_FILE" >&2; exit 6; }

install -d -m 0700 "$(dirname "$key_file")"
if [[ ! -f "$key_file" ]]; then
  umask 0177
  openssl rand -hex 32 > "$key_file"
fi
chmod 0600 "$key_file"

CPU_TARGET="$CPU_TARGET" LLAMA_CPP_SOURCE_DIR="$source_dir" LLAMA_CPP_BUILD_DIR="$project_dir/build/llama.cpp" \
  "$project_dir/scripts/build-llama.sh"

sudo -n install -m 0644 "$project_dir/deploy/cpu-inference.service" /etc/systemd/system/cpu-inference.service
sudo -n systemctl daemon-reload
sudo -n systemctl disable --now pds4-fast@dolphin-cyber-8b-q4.service pds4-gateway.service
sudo -n systemctl disable --now pds4-flash.service || true
sudo -n systemctl enable --now cpu-inference.service
sudo -n systemctl --no-pager --full status cpu-inference.service
