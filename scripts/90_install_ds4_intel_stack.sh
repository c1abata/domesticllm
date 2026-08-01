#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_AI_HOME="${LOCAL_AI_HOME:-/opt/local-ai}"
ENV_DST="${ENV_DST:-/etc/local-ai-ds4-intel.env}"
SERVICE_DST="/etc/systemd/system/local-ai-ds4-intel.service"

VARIANT="auto"
PORT="8081"
HOST="127.0.0.1"
API_KEY="${LOCAL_AI_API_KEY:-}"
LAN_CIDR=""
CACHE_DIR=""
MODELS_DIR=""
SKIP_DOWNLOAD=0
SKIP_DS4_REFERENCE=0
SKIP_PREPARE=0
FORCE=0

usage() {
  cat <<'USAGE'
Usage:
  sudo bash scripts/90_install_ds4_intel_stack.sh [options]

Options:
  --variant auto|q2|uncensored-q2|q2-plain|q2q4-mixed|q4|q4-plain|pro-q2
  LOCAL_AI_API_KEY           optional secret from environment; otherwise generated
  --port PORT                service port, default 8081
  --host HOST                bind address, default 127.0.0.1
  --lan-cidr CIDR            optional UFW allow rule, example 100.64.1.25/32
  --tailnet-cidr CIDR        alias for --lan-cidr
  --tailnet-client-ip IP     allow one Tailscale client IP, expands to IP/32
  --cache-dir DIR            slot/KV cache dir, ideally on mounted SATA/NVMe
  --models-dir DIR           model dir, ideally on second mounted SATA/NVMe
  --skip-download            install service without downloading a model
  --skip-ds4-reference       skip upstream ds4 CPU diagnostic build
  --skip-prepare             skip Ubuntu/server prep step
  --force                    allow DS4 profile below the recommended RAM class
  -h, --help

Examples:
  sudo bash scripts/90_install_ds4_intel_stack.sh --variant q2 --tailnet-client-ip 100.64.1.25
  sudo -E bash scripts/90_install_ds4_intel_stack.sh --variant q4
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --variant) VARIANT="${2:?missing variant}"; shift 2 ;;
    --port) PORT="${2:?missing port}"; shift 2 ;;
    --host) HOST="${2:?missing host}"; shift 2 ;;
    --lan-cidr) LAN_CIDR="${2:?missing CIDR}"; shift 2 ;;
    --tailnet-cidr) LAN_CIDR="${2:?missing CIDR}"; shift 2 ;;
    --tailnet-client-ip) LAN_CIDR="${2:?missing Tailscale IP}/32"; shift 2 ;;
    --cache-dir) CACHE_DIR="${2:?missing cache dir}"; shift 2 ;;
    --models-dir) MODELS_DIR="${2:?missing models dir}"; shift 2 ;;
    --skip-download) SKIP_DOWNLOAD=1; shift ;;
    --skip-ds4-reference) SKIP_DS4_REFERENCE=1; shift ;;
    --skip-prepare) SKIP_PREPARE=1; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo bash $0" >&2; exit 1; }
[ -f "$ROOT/conf/local-ai-ds4-intel.env" ] || { echo "Run from the repository checkout." >&2; exit 1; }

mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
mem_gib="$((mem_kb / 1024 / 1024))"
cpus="$(nproc)"

choose_variant() {
  if [ "$VARIANT" != "auto" ]; then
    echo "$VARIANT"
    return
  fi
  if [ "$mem_gib" -ge 256 ]; then
    echo "q4"
  elif [ "$mem_gib" -ge 160 ]; then
    echo "q2q4-mixed"
  elif [ "$mem_gib" -ge 112 ]; then
    echo "q2"
  else
    echo "too-small"
  fi
}

VARIANT="$(choose_variant)"
case "$VARIANT" in
  q2|uncensored-q2|q2-plain) min_gib=112; cache_k="q4_0"; cache_v="q4_0"; ctx=8192; batch=128; ubatch=32 ;;
  q2q4-mixed) min_gib=150; cache_k="q4_0"; cache_v="q4_0"; ctx=8192; batch=128; ubatch=32 ;;
  q4|q4-plain) min_gib=240; cache_k="q8_0"; cache_v="q8_0"; ctx=8192; batch=128; ubatch=32 ;;
  pro-q2) min_gib=480; cache_k="q8_0"; cache_v="q8_0"; ctx=4096; batch=64; ubatch=16 ;;
  too-small)
    cat >&2 <<EOF
This host has about ${mem_gib} GiB RAM. Do not run DeepSeek V4 Flash here.
Use the default 3B/7B profile, or rerun with --force only for diagnostics.
EOF
    [ "$FORCE" -eq 1 ] || exit 1
    VARIANT="q2"; min_gib=0; cache_k="q4_0"; cache_v="q4_0"; ctx=4096; batch=64; ubatch=16
    ;;
  *) echo "Unsupported variant: $VARIANT" >&2; exit 2 ;;
esac

model_link="ds4flash.gguf"
request_model="ds4flash"
if [ "$VARIANT" = "pro-q2" ]; then
  model_link="ds4pro.gguf"
  request_model="ds4pro"
elif [ "$VARIANT" = "uncensored-q2" ]; then
  model_link="ds4flash-uncensored.gguf"
  request_model="ds4flash-uncensored"
fi

if [ "$mem_gib" -lt "$min_gib" ] && [ "$FORCE" -ne 1 ]; then
  echo "Host RAM ${mem_gib} GiB is below recommended class for $VARIANT (${min_gib} GiB)." >&2
  echo "Pick a smaller variant or use --force for diagnostics only." >&2
  exit 1
fi

threads="$cpus"
if [ "$threads" -gt 32 ]; then threads=32; fi
if [ "$threads" -lt 1 ]; then threads=1; fi

echo "[info] RAM: ${mem_gib} GiB, CPU threads: ${cpus}, selected DS4 GGUF variant: ${VARIANT}"

if [ "$SKIP_PREPARE" -eq 0 ]; then
  prepare_args=()
  [ -n "$CACHE_DIR" ] && prepare_args+=(--cache-dir "$CACHE_DIR")
  [ -n "$MODELS_DIR" ] && prepare_args+=(--models-dir "$MODELS_DIR")
  bash "$ROOT/scripts/05_prepare_ubuntu_server.sh" "${prepare_args[@]}"
else
  bash "$ROOT/scripts/00_install_base.sh"
fi
bash "$ROOT/scripts/10_install_llamacpp_cpu.sh"
bash "$ROOT/scripts/20_install_antirez_tools.sh"
if [ "$SKIP_DS4_REFERENCE" -eq 0 ]; then
  bash "$ROOT/scripts/11_install_ds4_cpu_reference.sh"
else
  echo "[skip] ds4 CPU reference build"
fi

if [ -z "$API_KEY" ]; then
  API_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
fi
case "$API_KEY" in
  (*$'\n'*|*$'\r'*) echo "API key must not contain CR/LF" >&2; exit 2 ;;
esac

if [ "$SKIP_DOWNLOAD" -eq 0 ]; then
  bash "$ROOT/scripts/32_fetch_ds4_flash_gguf.sh" "$VARIANT"
else
  echo "[skip] model download"
fi

install -d -o localai -g localai -m 750 /var/cache/local-ai/ds4-slots
install -m 0644 "$ROOT/systemd/local-ai-ds4-intel.service" "$SERVICE_DST"
install -m 0755 "$ROOT/scripts/local-ai.sh" /usr/local/bin/local-ai
install -m 0555 "$ROOT/scripts/domesticllm-tui.py" /usr/local/bin/domesticllm-tui

cat > "$ENV_DST" <<EOF
LOCAL_AI_HOME=$LOCAL_AI_HOME
LOCAL_AI_MODEL=$LOCAL_AI_HOME/models/$model_link
LOCAL_AI_REQUEST_MODEL=$request_model
LOCAL_AI_HOST=$HOST
LOCAL_AI_PORT=$PORT
LOCAL_AI_API_KEY_FILE=/etc/local-ai-ds4-intel.key
LOCAL_AI_THREADS=$threads
LOCAL_AI_THREADS_BATCH=$threads
LOCAL_AI_CTX=$ctx
LOCAL_AI_PREDICT=1536
LOCAL_AI_BATCH=$batch
LOCAL_AI_UBATCH=$ubatch
LOCAL_AI_PARALLEL=1
LOCAL_AI_SLOTS=1
LOCAL_AI_SLOT_SAVE_PATH=/var/cache/local-ai/ds4-slots
LOCAL_AI_CACHE_TYPE_K=$cache_k
LOCAL_AI_CACHE_TYPE_V=$cache_v
LOCAL_AI_CACHE_REUSE=512
LOCAL_AI_KEEP=-1
LOCAL_AI_EXTRA_ARGS=
EOF
chmod 0640 "$ENV_DST"
chown root:localai "$ENV_DST"
printf '%s\n' "$API_KEY" > /etc/local-ai-ds4-intel.key
chmod 0640 /etc/local-ai-ds4-intel.key
chown root:localai /etc/local-ai-ds4-intel.key

systemctl daemon-reload
systemctl enable --now local-ai-ds4-intel

if [ -n "$LAN_CIDR" ]; then
  bash "$ROOT/scripts/40_firewall_lan.sh" "$LAN_CIDR" "$PORT"
fi

echo "[info] waiting for service health"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "[ok] local-ai-ds4-intel is healthy on port $PORT"
    break
  fi
  sleep 2
done

if ! curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "[error] service failed health; inspect: journalctl -u local-ai-ds4-intel -n 100 --no-pager" >&2
  exit 1
fi

echo "[ok] DS4 Intel profile installed"
echo "[info] env: $ENV_DST"
echo "[info] tui: local-ai tui"
echo "[info] ask: ENV_FILE=$ENV_DST bash scripts/50_ask.sh 'Rispondi solo OK'"
