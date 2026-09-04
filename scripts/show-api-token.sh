#!/usr/bin/env bash
set -euo pipefail
token=/home/ale/.local/state/cpu-inference/api.token
[[ -r "$token" ]] || { echo "API token not created yet; start cpu-inference-lan-gateway.service first." >&2; exit 1; }
cat "$token"
