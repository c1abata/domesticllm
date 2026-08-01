#!/usr/bin/env bash
set -euo pipefail

LOCAL_AI_HOME="${LOCAL_AI_HOME:-/opt/local-ai}"
MODEL_DIR="${MODEL_DIR:-$LOCAL_AI_HOME/models}"
VARIANT="${1:-q2}"
REPOSITORY=antirez/deepseek-v4-gguf
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../conf/vendor-refs.env
. "$ROOT/conf/vendor-refs.env"

case "$VARIANT" in
  q2)
    FILE="$DS4_Q2_IMATRIX_FILE"
    REVISION="$DS4_Q2_IMATRIX_REVISION"
    EXPECTED_SHA256="$DS4_Q2_IMATRIX_SHA256"
    MIN_RAM="128 GB"
    ;;
  uncensored-q2)
    REPOSITORY="$DS4_UNCENSORED_REPOSITORY"
    FILE="$DS4_UNCENSORED_Q2_FILE"
    REVISION="$DS4_UNCENSORED_Q2_REVISION"
    EXPECTED_SHA256="$DS4_UNCENSORED_Q2_SHA256"
    MIN_RAM="128 GB; experimental controlled-local-use model"
    ;;
  q2-plain)
    FILE="DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2.gguf"
    MIN_RAM="128 GB"
    ;;
  q2q4-mixed)
    FILE="DeepSeek-V4-Flash-Layers37-42Q4KExperts-OtherExpertLayersIQ2XXSGateUp-Q2KDown-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix-fixed.gguf"
    MIN_RAM="160 GB"
    ;;
  q4)
    FILE="DeepSeek-V4-Flash-Q4KExperts-F16HC-F16Compressor-F16Indexer-Q8Attn-Q8Shared-Q8Out-chat-v2-imatrix.gguf"
    MIN_RAM="256 GB"
    ;;
  q4-plain)
    FILE="DeepSeek-V4-Flash-Q4KExperts-F16HC-F16Compressor-F16Indexer-Q8Attn-Q8Shared-Q8Out-chat-v2.gguf"
    MIN_RAM="256 GB"
    ;;
  mtp)
    FILE="DeepSeek-V4-Flash-MTP-Q4K-Q8_0-F32.gguf"
    MIN_RAM="optional"
    ;;
  pro-q2)
    FILE="DeepSeek-V4-Pro-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-Instruct-imatrix.gguf"
    MIN_RAM="512 GB"
    ;;
  *)
    echo "Usage: $0 {q2|uncensored-q2|q2-plain|q2q4-mixed|q4|q4-plain|mtp|pro-q2}" >&2
    exit 2
    ;;
esac

if [ "$VARIANT" = q2 ] || [ "$VARIANT" = uncensored-q2 ]; then
  [ -z "${DS4_MODEL_REVISION:-}" ] || [ "$DS4_MODEL_REVISION" = "$REVISION" ] || {
    echo "The locked q2 revision cannot be overridden" >&2; exit 1;
  }
  [ -z "${DS4_MODEL_SHA256:-}" ] || [ "$DS4_MODEL_SHA256" = "$EXPECTED_SHA256" ] || {
    echo "The locked q2 SHA-256 cannot be overridden" >&2; exit 1;
  }
else
  REVISION="${DS4_MODEL_REVISION:-}"
  EXPECTED_SHA256="${DS4_MODEL_SHA256:-}"
fi
[ -n "$REVISION" ] && [ "${#REVISION}" -eq 40 ] || {
  echo "A locked 40-character DS4_MODEL_REVISION is required for $VARIANT" >&2
  exit 1
}
[ -n "$EXPECTED_SHA256" ] && [ "${#EXPECTED_SHA256}" -eq 64 ] || {
  echo "A locked 64-character DS4_MODEL_SHA256 is required for $VARIANT" >&2
  exit 1
}
URL="https://huggingface.co/$REPOSITORY/resolve/$REVISION/$FILE"
PART="$MODEL_DIR/$FILE.part"
FINAL="$MODEL_DIR/$FILE"

if [ "$(id -u)" -eq 0 ] && [ "${DS4_DOWNLOAD_WORKER:-0}" != 1 ]; then
  id localai-build >/dev/null 2>&1 || { echo "Missing build account localai-build" >&2; exit 1; }
  if command -v systemctl >/dev/null 2>&1; then
    for unit in local-ai-ds4-native.service local-ai-ds4-nvidia.service local-ai-ds4-intel.service; do
      if systemctl is-active --quiet "$unit"; then
        echo "Refusing model download while $unit is active" >&2
        exit 1
      fi
    done
  fi
  install -d -o root -g root -m 0755 "$MODEL_DIR"
  model_dir_real="$(readlink -f "$MODEL_DIR")"
  chown root:root "$model_dir_real"
  chmod 0755 "$model_dir_real"
  FINAL="$model_dir_real/$FILE"
  if [ -f "$FINAL" ] && [ "$(sha256sum "$FINAL" | awk '{print $1}')" = "$EXPECTED_SHA256" ]; then
    chown root:localai "$FINAL"
    chmod 0440 "$FINAL"
    echo "[skip] verified model already present: $FINAL"
    exit 0
  fi
  if [ -f "$FINAL" ]; then
    install -d -o root -g root -m 0750 "$model_dir_real/quarantine"
    mv "$FINAL" "$model_dir_real/quarantine/$(date -u +%Y%m%dT%H%M%SZ)-$FILE.bad"
  fi
  staging="$model_dir_real/.staging/$VARIANT"
  install -d -o root -g root -m 0755 "$model_dir_real/.staging"
  install -d -o localai-build -g localai-build -m 0750 "$staging"
  chown -R localai-build:localai-build "$staging"
  harden_staging() {
    chown -R root:root "$staging" 2>/dev/null || true
    chmod -R go-w "$staging" 2>/dev/null || true
  }
  trap harden_staging EXIT
  if ! runuser -u localai-build -- env \
    LOCAL_AI_HOME="$LOCAL_AI_HOME" MODEL_DIR="$staging" DS4_DOWNLOAD_WORKER=1 \
    DS4_MODEL_REVISION="${DS4_MODEL_REVISION:-}" \
    DS4_MODEL_SHA256="${DS4_MODEL_SHA256:-}" \
    bash "$0" "$VARIANT"; then
    echo "Download failed; staging evidence was made root-owned" >&2
    exit 1
  fi
  staged_final="$staging/$FILE"
  [ "$(sha256sum "$staged_final" | awk '{print $1}')" = "$EXPECTED_SHA256" ] || {
    echo "Root verification rejected staged model" >&2; exit 1;
  }
  temporary="$model_dir_real/.${FILE}.install.$$"
  mv "$staged_final" "$temporary"
  chown root:localai "$temporary"
  chmod 0440 "$temporary"
  mv -Tf "$temporary" "$FINAL"
  if [ "$VARIANT" = "pro-q2" ]; then
    ln -sfn "$FINAL" "$model_dir_real/ds4pro.gguf"
    chown -h root:root "$model_dir_real/ds4pro.gguf"
  elif [ "$VARIANT" = "uncensored-q2" ]; then
    ln -sfn "$FINAL" "$model_dir_real/ds4flash-uncensored.gguf"
    chown -h root:root "$model_dir_real/ds4flash-uncensored.gguf"
  elif [ "$VARIANT" != "mtp" ]; then
    ln -sfn "$FINAL" "$model_dir_real/ds4flash.gguf"
    chown -h root:root "$model_dir_real/ds4flash.gguf"
  fi
  harden_staging
  trap - EXIT
  echo "[ok] model ownership hardened for service use"
  exit 0
fi

[ "${DS4_DOWNLOAD_WORKER:-0}" = 1 ] || {
  echo "Run as root; the network transfer is delegated to unprivileged localai-build" >&2
  exit 1
}

mkdir -p "$MODEL_DIR"
echo "[info] downloading $FILE"
echo "[info] expected RAM class: $MIN_RAM"
curl -L --fail --continue-at - --output "$PART" "$URL"
ACTUAL_SHA256="$(sha256sum "$PART" | awk '{print $1}')"
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  quarantine="$MODEL_DIR/quarantine/$(date -u +%Y%m%dT%H%M%SZ)-$FILE.part"
  install -d -m 0750 "$MODEL_DIR/quarantine"
  mv "$PART" "$quarantine"
  echo "Model checksum mismatch; quarantined at $quarantine" >&2
  exit 1
fi
mv "$PART" "$FINAL"

chmod 0440 "$FINAL"
echo "[ok] downloaded and verified $FINAL"
