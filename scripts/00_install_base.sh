#!/usr/bin/env bash
set -euo pipefail
LOCAL_AI_HOME="${LOCAL_AI_HOME:-/opt/local-ai}"
[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo bash $0" >&2; exit 1; }
apt-get update
apt-get install -y build-essential cmake git curl jq pkg-config libopenblas-dev libcurl4-openssl-dev libsqlite3-dev ufw ethtool ca-certificates python3
id -u localai >/dev/null 2>&1 || useradd --system --create-home --home-dir "$LOCAL_AI_HOME" --shell /usr/sbin/nologin localai
id -u localai-build >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin localai-build
install -d -o root -g root -m 0755 "$LOCAL_AI_HOME" "$LOCAL_AI_HOME/bin" "$LOCAL_AI_HOME/models"
install -d -o localai-build -g localai-build -m 0750 \
  "$LOCAL_AI_HOME/src" "$LOCAL_AI_HOME/tools" "$LOCAL_AI_HOME/repos"
install -d -o localai -g localai -m 0750 /var/cache/local-ai/slots /var/log/local-ai
echo "[ok] base installed"
