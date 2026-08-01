#!/usr/bin/env bash
set -euo pipefail
SRC="${1:?Usage: $0 CIDR PORT. Example: $0 192.168.1.50/32 8080}"
PORT="${2:-8080}"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH || ufw allow 22/tcp
ufw allow from "$SRC" to any port "$PORT" proto tcp
ufw --force enable
ufw status verbose
