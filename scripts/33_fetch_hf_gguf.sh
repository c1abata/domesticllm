#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
This optional downloader is disabled by supply-chain policy.

The previous implementation used moving Hugging Face branches and validated
only Content-Length. Add an immutable revision plus SHA-256 for every shard to
vendor.lock.json before re-enabling a model. The critical DS4 q2-imatrix path is:

  bash scripts/32_fetch_ds4_flash_gguf.sh q2
EOF
exit 1
