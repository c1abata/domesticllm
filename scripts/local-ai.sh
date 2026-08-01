#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$SCRIPT_DIR" = /usr/local/bin ] && [ -d /usr/local/libexec/local-ai/scripts ]; then
  ROOT=/usr/local/libexec/local-ai
else
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
ENV_FILE="${ENV_FILE:-/etc/local-ai-ds4-intel.env}"
SERVICE="${SERVICE:-local-ai-ds4-intel}"

load_env() {
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  fi
}

client_host() {
  local host="${LOCAL_AI_HOST:-127.0.0.1}"
  case "$host" in
    0.0.0.0|::) echo "127.0.0.1" ;;
    *) echo "$host" ;;
  esac
}

base_url() {
  local host port
  host="$(client_host)"
  port="${LOCAL_AI_PORT:-8081}"
  echo "${LOCAL_AI_BASE_URL:-http://${host}:${port}/v1}"
}

require_root() {
  [ "$(id -u)" -eq 0 ] || {
    echo "Serve root: sudo $0 $*" >&2
    exit 1
  }
}

usage() {
  cat <<'USAGE'
Usage:
  local-ai <command> [args]

Core:
  tui                         menu interattivo minimale
  status                      stato servizio, health, RAM, socket, cache
  ask "prompt"                domanda one-shot via API OpenAI-compatible
  logs                        ultimi log systemd
  start|stop|restart          controlla il servizio systemd

Install:
  install-ds4 [args]          wrapper per scripts/90_install_ds4_intel_stack.sh
  install-ds4-nvidia [args]   wrapper per scripts/90_install_ds4_nvidia_stack.sh
  install --backend ds4 --artifact DIR [--start-canary]
  install-cli                 installa questo launcher in /usr/local/bin/local-ai
  opencode-config             genera config opencode senza incorporare segreti
  powershell-hint             stampa uso client Windows/PowerShell via env

Ops:
  doctor                      preflight host/release/modello DS4 nativo
  benchmark --suite acceptance ARGS
                              benchmark identico DS4/llama con evidenze
  promote ds4 --acceptance-file FILE --confirm PROMOTE_DS4
  rollback llama --confirm ROLLBACK_LLAMA
  decision                    mostra prerequisiti e dati mancanti
  model                       mostra modello linkato e spazio occupato
  cache                       mostra cache slot/KV su SSD

Env:
  ENV_FILE=/path/file         default /etc/local-ai-ds4-intel.env
  SERVICE=name               default local-ai-ds4-intel
USAGE
}

cmd_status() {
  load_env
  local base health
  base="$(base_url)"
  health="${base%/v1}/health"
  echo "== env =="
  echo "ENV_FILE=$ENV_FILE"
  echo "SERVICE=$SERVICE"
  echo "BASE=$base"
  echo "MODEL=${LOCAL_AI_MODEL:-unset}"
  echo
  echo "== service =="
  systemctl is-active "$SERVICE" || true
  systemctl --no-pager --full status "$SERVICE" 2>/dev/null | sed -n '1,12p' || true
  echo
  echo "== health =="
  curl -fsS "$health" 2>/dev/null || echo "health unavailable"
  echo
  echo "== memory =="
  free -h || true
  echo
  echo "== socket =="
  ss -lntp 2>/dev/null | grep ":${LOCAL_AI_PORT:-8081}" || true
  echo
  cmd_cache
}

cmd_ask() {
  load_env
  local prompt="${*:-}"
  [ -n "$prompt" ] || { echo "Usage: local-ai ask \"prompt\"" >&2; exit 1; }
  "$ROOT/scripts/50_ask.sh" "$prompt"
}

cmd_logs() {
  journalctl -u "$SERVICE" -n 120 --no-pager
}

cmd_service() {
  require_root "$@"
  systemctl "$1" "$SERVICE"
}

cmd_install_cli() {
  require_root "$@"
  install -m 0755 "$ROOT/scripts/local-ai.sh" /usr/local/bin/local-ai
  echo "[ok] installed /usr/local/bin/local-ai"
}

cmd_install_ds4() {
  require_root "$@"
  bash "$ROOT/scripts/90_install_ds4_intel_stack.sh" "$@"
  cmd_install_cli
}

cmd_install_ds4_nvidia() {
  require_root "$@"
  bash "$ROOT/scripts/90_install_ds4_nvidia_stack.sh" "$@"
  cmd_install_cli
}

cmd_opencode_config() {
  mkdir -p "$HOME/.config/opencode/agents"
  cp "$ROOT/opencode/opencode.ds4-intel-lan.json" "$HOME/.config/opencode/opencode.json"
  cp "$ROOT"/agents/*.md "$HOME/.config/opencode/agents/"
  chmod 0600 "$HOME/.config/opencode/opencode.json"
  echo "[ok] wrote $HOME/.config/opencode/opencode.json"
  echo "[next] export LOCAL_AI_BASE_URL and LOCAL_AI_API_KEY before OpenCode"
}

cmd_powershell_hint() {
  cat <<'EOF'
$env:LOCAL_AI_BASE_URL = 'http://127.0.0.1:8083/v1'
$secret = Read-Host 'LOCAL_AI_API_KEY' -AsSecureString
$env:LOCAL_AI_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
powershell -ExecutionPolicy Bypass -File .\\scripts\\local-ai-client.ps1 \\
  -ConfigureOpenCode

powershell -ExecutionPolicy Bypass -File .\\scripts\\local-ai-client.ps1 \\
  -Prompt 'Rispondi solo OK'
EOF
}

helper_path() {
  shift
  local repo="$1"
  if [ -x "/usr/local/libexec/local-ai/scripts/$repo" ]; then
    printf '%s\n' "/usr/local/libexec/local-ai/scripts/$repo"
  else
    printf '%s\n' "$ROOT/scripts/$repo"
  fi
}

cmd_doctor() {
  "$(helper_path ds4-health 16_ds4_health.sh)" doctor "$@"
}

cmd_install_native() {
  [ "${1:-}" = "--backend" ] && [ "${2:-}" = "ds4" ] || {
    echo "Usage: local-ai install --backend ds4 --artifact DIR [--start-canary]" >&2
    exit 2
  }
  shift 2
  require_root "$@"
  "$(helper_path ds4-install 15_install_ds4_native.sh)" "$@"
}

cmd_benchmark_acceptance() {
  [ "${1:-}" = "--suite" ] && [ "${2:-}" = "acceptance" ] || {
    echo "Usage: local-ai benchmark --suite acceptance [args]" >&2
    exit 2
  }
  shift 2
  "$(helper_path ds4-benchmark 17_benchmark_ds4_acceptance.sh)" "$@"
}

cmd_promote_native() {
  [ "${1:-}" = "ds4" ] || { echo "Usage: local-ai promote ds4 --acceptance-file FILE --confirm PROMOTE_DS4" >&2; exit 2; }
  shift
  require_root "$@"
  "$(helper_path ds4-promote 18_promote_ds4_native.sh)" "$@"
}

cmd_rollback_llama() {
  [ "${1:-}" = "llama" ] || { echo "Usage: local-ai rollback llama --confirm ROLLBACK_LLAMA" >&2; exit 2; }
  shift
  require_root "$@"
  "$(helper_path llama-rollback 19_rollback_llama.sh)" "$@"
}

cmd_decision() {
  cat <<'EOF'
== decision gate ==
DeepSeek V4 Flash su CPU Intel/AMD e' fattibile solo come profilo lento e RAM-heavy.
La classe CPU conta meno della RAM: Xeon/Core/Ryzen/EPYC entry-level vanno trattati come nodi CPU-only.
Default operativo: agente PowerShell sul laptop, inferenza su Ubuntu Server via Tailscale.

Decisione corrente:
- OS server: Ubuntu Server 24.04 LTS; 26.04 LTS accettata se serve kernel piu' nuovo.
- RAM ipotizzata: 128 GiB.
- Modello: q2 imatrix.
- Dischi: 2 SATA da almeno 256 GB, gia' montati; uno per cache/slot, uno per modelli.
- Rete: Tailscale, IP client inserito durante install con --tailnet-client-ip.

Dati da inserire durante install:
- Tailscale IP del laptop/client PowerShell.
- Mount path disco cache, esempio /mnt/sata-cache/local-ai/ds4-slots.
- Mount path disco modelli, esempio /mnt/sata-models/local-ai/models.
- Hugging Face: token solo se il download pubblico fallisce o cambia policy.

Comando consigliato:
sudo bash scripts/90_install_ds4_intel_stack.sh --variant q2 \
  --tailnet-client-ip 100.x.y.z \
  --cache-dir /mnt/sata-cache/local-ai/ds4-slots \
  --models-dir /mnt/sata-models/local-ai/models

Linea dura:
- <112 GiB RAM: non DS4 Flash; usa profilo 3B/7B.
- 128 GiB: q2 imatrix, ctx 8192, batch 128, parallel 1.
- Ryzen 9 5950X + 2x RTX A4500: usa scripts/90_install_ds4_nvidia_stack.sh, porta 8082.
- 160 GiB: q2q4 mixed solo dopo test q2 stabile.
- 256 GiB+: q4 imatrix.
- CPU-only ds4 nativo: build diagnostico, non servizio di produzione.
EOF
}

cmd_model() {
  load_env
  local model="${LOCAL_AI_MODEL:-}"
  [ -n "$model" ] || { echo "LOCAL_AI_MODEL unset"; exit 1; }
  ls -lh "$model" 2>/dev/null || true
  if [ -L "$model" ]; then readlink -f "$model"; fi
  du -h "$model" 2>/dev/null || true
}

cmd_cache() {
  load_env
  local dir="${LOCAL_AI_SLOT_SAVE_PATH:-/var/cache/local-ai/ds4-slots}"
  echo "== cache =="
  echo "$dir"
  du -h "$dir" 2>/dev/null || true
  find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l | awk '{print "files="$1}' || true
}

cmd_tui() {
  while true; do
    cat <<'MENU'

local-ai TUI
1) status
2) ask
3) logs
4) restart service
5) model
6) cache
7) decision gate
8) install DS4 Intel stack
9) install DS4 NVIDIA stack
10) quit
MENU
    printf '> '
    read -r choice
    case "$choice" in
      1) cmd_status ;;
      2) printf 'prompt> '; read -r prompt; cmd_ask "$prompt" ;;
      3) cmd_logs ;;
      4) cmd_service restart ;;
      5) cmd_model ;;
      6) cmd_cache ;;
      7) cmd_decision ;;
      8) echo "Esempio: sudo local-ai install-ds4 --variant auto --lan-cidr TAILNET_IP/32" ;;
      9) echo "Esempio: sudo local-ai install-ds4-nvidia --variant q2 --tailnet-client-ip TAILNET_IP" ;;
      10|q|quit|exit) exit 0 ;;
      *) echo "scelta non valida" ;;
    esac
  done
}

cmd="${1:-tui}"
shift || true

case "$cmd" in
  tui) cmd_tui "$@" ;;
  status) cmd_status "$@" ;;
  ask) cmd_ask "$@" ;;
  logs) cmd_logs "$@" ;;
  start|stop|restart) cmd_service "$cmd" ;;
  install-cli) cmd_install_cli "$@" ;;
  install-ds4) cmd_install_ds4 "$@" ;;
  install-ds4-nvidia) cmd_install_ds4_nvidia "$@" ;;
  install) cmd_install_native "$@" ;;
  doctor) cmd_doctor "$@" ;;
  benchmark) cmd_benchmark_acceptance "$@" ;;
  promote) cmd_promote_native "$@" ;;
  rollback) cmd_rollback_llama "$@" ;;
  opencode-config) cmd_opencode_config "$@" ;;
  powershell-hint) cmd_powershell_hint "$@" ;;
  decision) cmd_decision "$@" ;;
  model) cmd_model "$@" ;;
  cache) cmd_cache "$@" ;;
  -h|--help|help) usage ;;
  *) echo "Unknown command: $cmd" >&2; usage >&2; exit 2 ;;
esac
