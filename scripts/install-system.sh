#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  printf 'run as root: sudo scripts/install-system.sh\n' >&2
  exit 2
fi

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
config_file=${CPU_INFERENCE_CONFIG:-"$project_dir/config/cpu-inference.env"}

[[ -r "$config_file" ]] || {
  printf 'missing configuration: %s\n' "$config_file" >&2
  exit 3
}

# shellcheck disable=SC1090
source "$config_file"
: "${MODEL:?MODEL is required}"
: "${MODEL_SHA256:?MODEL_SHA256 is required}"
: "${CPU_TARGET:?CPU_TARGET is required}"
[[ -r "$MODEL" ]] || { printf 'model not readable: %s\n' "$MODEL" >&2; exit 4; }

install -d -m 0755 /opt/cpu-inference /etc/cpu-inference /var/lib/cpu-inference
install -m 0644 "$project_dir/README.md" /opt/cpu-inference/README.md
install -d -m 0755 /opt/cpu-inference/scripts
install -m 0755 "$project_dir/scripts/build-llama.sh" /opt/cpu-inference/scripts/build-llama.sh
install -m 0755 "$project_dir/scripts/run-server.sh" /opt/cpu-inference/scripts/run-server.sh

if ! getent group cpu-inference >/dev/null; then
  groupadd --system cpu-inference
fi
if ! id -u cpu-inference >/dev/null 2>&1; then
  useradd --system --gid cpu-inference --home-dir /var/lib/cpu-inference --shell /usr/sbin/nologin cpu-inference
fi

install -m 0640 -o root -g cpu-inference "$config_file" /etc/cpu-inference/cpu-inference.env

if [[ -n "${API_KEY_FILE:-}" ]]; then
  [[ -f "$API_KEY_FILE" ]] || { printf 'API key file missing: %s\n' "$API_KEY_FILE" >&2; exit 5; }
  chown root:cpu-inference "$API_KEY_FILE"
  chmod 0640 "$API_KEY_FILE"
fi

source_dir=${LLAMA_CPP_SOURCE_DIR:-}
[[ -n "$source_dir" ]] || {
  printf 'LLAMA_CPP_SOURCE_DIR is required; use a reviewed local llama.cpp source checkout.\n' >&2
  exit 6
}
CPU_TARGET="$CPU_TARGET" LLAMA_CPP_SOURCE_DIR="$source_dir" LLAMA_CPP_BUILD_DIR=/opt/cpu-inference/build/llama.cpp \
  /opt/cpu-inference/scripts/build-llama.sh

install -m 0644 "$project_dir/deploy/cpu-inference.service" /etc/systemd/system/cpu-inference.service
systemctl daemon-reload
systemctl enable cpu-inference.service
systemctl restart cpu-inference.service
systemctl --no-pager --full status cpu-inference.service
