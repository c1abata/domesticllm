#!/usr/bin/env bash
set -euo pipefail
LOCAL_AI_HOME="${LOCAL_AI_HOME:-/opt/local-ai}"
REPO="$LOCAL_AI_HOME/repos/qwen-asr"
[ -d "$REPO" ] || { echo "qwen-asr repository missing. Run scripts/20_install_antirez_tools.sh first."; exit 1; }
if [ -f "$REPO/Makefile" ]; then make -C "$REPO" blas || make -C "$REPO" || true; find "$REPO" -maxdepth 2 -type f -perm -111 -name '*qwen*' -exec cp {} "$LOCAL_AI_HOME/bin/" \; || true; fi
echo "[ok] qwen-asr attempted build"
