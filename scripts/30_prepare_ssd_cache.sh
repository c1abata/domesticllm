#!/usr/bin/env bash
set -euo pipefail
DIR="${1:-/var/cache/local-ai/slots}"
mkdir -p "$DIR"
chown -R localai:localai "$DIR"
chmod 750 "$DIR"
sync
echo "[ok] SSD slot cache directory: $DIR"
