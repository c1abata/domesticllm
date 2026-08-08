#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH_TARGET=""
LOCAL_PORT=18080
REMOTE_PORT=8080
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
INSTALL_ONLY=0

usage() {
  cat <<'EOF'
Usage: scripts/28_configure_hermes_wsl.sh --ssh-target USER@HOST [options]

Installs an unprivileged systemd-user SSH tunnel definition and DomesticLLM
Hermes examples. It does not install Hermes, copy secrets, start services, or
change the server.

Options:
  --ssh-target USER@HOST   required SSH destination on the private tailnet
  --local-port PORT        local gateway port, default 18080
  --remote-port PORT       server gateway port, default 8080
  --config-home DIR        default $XDG_CONFIG_HOME or ~/.config
  --install-only           skip live prerequisites and tunnel checks
EOF
}

valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ssh-target) SSH_TARGET="${2:?missing SSH target}"; shift 2 ;;
    --local-port) LOCAL_PORT="${2:?missing local port}"; shift 2 ;;
    --remote-port) REMOTE_PORT="${2:?missing remote port}"; shift 2 ;;
    --config-home) CONFIG_HOME="${2:?missing config home}"; shift 2 ;;
    --install-only) INSTALL_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[ "$(id -u)" -ne 0 ] || { echo "run as the WSL user, not root" >&2; exit 1; }
[ -n "$SSH_TARGET" ] || { usage >&2; exit 2; }
case "$SSH_TARGET" in
  *[!A-Za-z0-9_.@:-]*|-*|*@*@*) echo "invalid SSH target" >&2; exit 2 ;;
esac
valid_port "$LOCAL_PORT" || { echo "invalid local port" >&2; exit 2; }
valid_port "$REMOTE_PORT" || { echo "invalid remote port" >&2; exit 2; }

for command in install ssh; do
  command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 1; }
done
if [ "$INSTALL_ONLY" -eq 0 ]; then
  command -v hermes >/dev/null || {
    echo "Hermes is not installed. Review and install it separately, then rerun." >&2
    exit 1
  }
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_TARGET" true || {
    echo "SSH preflight failed; configure the dedicated key before installing the tunnel." >&2
    exit 1
  }
fi

domestic_dir="$CONFIG_HOME/domesticllm"
unit_dir="$CONFIG_HOME/systemd/user"
install -d -m 0700 "$domestic_dir" "$unit_dir"
install -m 0600 /dev/null "$domestic_dir/tunnel.env"
printf 'DOMESTICLLM_LOCAL_BIND=127.0.0.1:%s\nDOMESTICLLM_REMOTE_BIND=127.0.0.1:%s\nDOMESTICLLM_SSH_TARGET=%s\n' \
  "$LOCAL_PORT" "$REMOTE_PORT" "$SSH_TARGET" >"$domestic_dir/tunnel.env"
install -m 0644 "$ROOT/systemd/user/domesticllm-hermes-tunnel.service" \
  "$unit_dir/domesticllm-hermes-tunnel.service"
install -m 0600 "$ROOT/examples/hermes/config.yaml" "$domestic_dir/hermes-config.yaml.example"
install -m 0600 "$ROOT/examples/hermes/hermes.env.example" "$domestic_dir/hermes.env.example"

cat <<EOF
[ok] installed user tunnel definition
[next] review $domestic_dir/tunnel.env
[next] copy the gateway key and Telegram token into ~/.hermes/.env (mode 0600)
[next] merge $domestic_dir/hermes-config.yaml.example into ~/.hermes/config.yaml
[gate] after review: systemctl --user daemon-reload && systemctl --user enable --now domesticllm-hermes-tunnel
[test] curl -fsS -H 'Authorization: Bearer <key>' http://127.0.0.1:${LOCAL_PORT}/v1/models
[telegram] hermes gateway setup && hermes gateway start
EOF
