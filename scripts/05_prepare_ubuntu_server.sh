#!/usr/bin/env bash
set -euo pipefail

LOCAL_AI_HOME="${LOCAL_AI_HOME:-/opt/local-ai}"
CACHE_DIR="/var/cache/local-ai/ds4-slots"
MODELS_DIR="$LOCAL_AI_HOME/models"
ALLOW_UBUNTU_DEV=0

usage() {
  cat <<'USAGE'
Usage:
  sudo bash scripts/05_prepare_ubuntu_server.sh [options]

Options:
  --cache-dir DIR       cache/slot directory, ideally on mounted SATA/NVMe
  --models-dir DIR      model directory, ideally on second mounted SATA/NVMe
  --allow-ubuntu-dev    allow Ubuntu releases outside 24.04/26.04 LTS
  -h, --help

Example with two mounted SATA disks:
  sudo bash scripts/05_prepare_ubuntu_server.sh \
    --cache-dir /mnt/sata-cache/local-ai/ds4-slots \
    --models-dir /mnt/sata-models/local-ai/models
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --cache-dir) CACHE_DIR="${2:?missing cache dir}"; shift 2 ;;
    --models-dir) MODELS_DIR="${2:?missing models dir}"; shift 2 ;;
    --allow-ubuntu-dev) ALLOW_UBUNTU_DEV=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo bash $0" >&2; exit 1; }

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}:${VERSION_ID:-}" in
    ubuntu:24.04|ubuntu:26.04) ;;
    *)
      if [ "$ALLOW_UBUNTU_DEV" -ne 1 ]; then
        echo "Recommended OS: Ubuntu Server 24.04 LTS. Also accepted: 26.04 LTS." >&2
        echo "Detected: ${PRETTY_NAME:-unknown}. Use --allow-ubuntu-dev to continue." >&2
        exit 1
      fi
      ;;
  esac
fi

apt-get update
apt-get install -y \
  build-essential cmake git curl jq pkg-config \
  libopenblas-dev libcurl4-openssl-dev libsqlite3-dev \
  ufw ethtool ca-certificates python3 htop iotop sysstat nvme-cli smartmontools

id -u localai >/dev/null 2>&1 || \
  useradd --system --create-home --home-dir "$LOCAL_AI_HOME" --shell /usr/sbin/nologin localai
id -u localai-build >/dev/null 2>&1 || \
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin localai-build

install -d -o root -g root -m 0755 \
  "$LOCAL_AI_HOME" "$LOCAL_AI_HOME/bin" "$MODELS_DIR"
install -d -o localai-build -g localai-build -m 0750 \
  "$LOCAL_AI_HOME/src" "$LOCAL_AI_HOME/tools" "$LOCAL_AI_HOME/repos"
install -d -o localai -g localai -m 0750 "$CACHE_DIR" /var/log/local-ai

replace_empty_with_symlink() {
  local target="$1" link="$2"
  if [ -L "$link" ]; then
    [ "$(readlink "$link")" = "$target" ] && return
    unlink "$link"
  elif [ -d "$link" ]; then
    rmdir "$link" || { echo "Refusing to replace non-empty directory: $link" >&2; exit 1; }
  elif [ -e "$link" ]; then
    echo "Refusing to replace non-directory path: $link" >&2
    exit 1
  fi
  ln -s "$target" "$link"
}

if [ "$MODELS_DIR" != "$LOCAL_AI_HOME/models" ]; then
  replace_empty_with_symlink "$MODELS_DIR" "$LOCAL_AI_HOME/models"
fi

if [ "$CACHE_DIR" != "/var/cache/local-ai/ds4-slots" ]; then
  install -d -o root -g root -m 0755 /var/cache/local-ai
  replace_empty_with_symlink "$CACHE_DIR" /var/cache/local-ai/ds4-slots
fi

cat >/etc/sysctl.d/99-local-ai-poorhw.conf <<'EOF'
vm.swappiness=10
vm.dirty_background_ratio=5
vm.dirty_ratio=20
EOF
sysctl --system >/dev/null || true

if command -v systemctl >/dev/null 2>&1; then
  systemctl enable --now sysstat >/dev/null 2>&1 || true
fi

echo "[ok] Ubuntu server prepared"
echo "[info] models: $MODELS_DIR"
echo "[info] cache:  $CACHE_DIR"
echo "[info] next: sudo bash scripts/90_install_ds4_intel_stack.sh --variant q2 --tailnet-client-ip YOUR_TAILSCALE_IP"
