#!/usr/bin/env bash
set -euo pipefail
umask 077

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY_FILE="${LOCAL_AI_GATEWAY_KEY_FILE:-/etc/local-ai-gateway.key}"
UNIT=domesticllm-lan-gateway.service
LAN_CIDR=""

usage() {
  echo "Usage: sudo $0 --lan-cidr CIDR" >&2
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --lan-cidr) LAN_CIDR="${2:?missing CIDR}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done
[ -n "$LAN_CIDR" ] || { usage; exit 2; }
LAN_CIDR="$(python3 -c 'import ipaddress,sys; print(ipaddress.ip_network(sys.argv[1], strict=False))' "$LAN_CIDR")" || {
  echo "invalid LAN CIDR" >&2
  exit 2
}

for command in install python3 systemctl; do
  command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 1; }
done
systemctl is-active --quiet local-ai-ds4-native.service || {
  echo "local-ai-ds4-native.service must be active" >&2
  exit 1
}

install -d -o root -g root -m 0755 /usr/local/libexec/local-ai
install -o root -g root -m 0555 "$ROOT/scripts/domesticllm-gateway.py" \
  /usr/local/libexec/local-ai/domesticllm-gateway
install -o root -g root -m 0444 "$ROOT/systemd/$UNIT" "/etc/systemd/system/$UNIT"
install -d -o root -g root -m 0755 "/etc/systemd/system/$UNIT.d"
dropin="$(mktemp)"
trap 'rm -f "$dropin"' EXIT
printf '[Service]\nIPAddressAllow=%s\n' "$LAN_CIDR" >"$dropin"
install -o root -g root -m 0444 "$dropin" "/etc/systemd/system/$UNIT.d/lan.conf"
if [ ! -e "$KEY_FILE" ]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(48))' >"$KEY_FILE"
fi
[ ! -L "$KEY_FILE" ] || { echo "refusing symlinked key file" >&2; exit 1; }
chown root:localai "$KEY_FILE"
chmod 0640 "$KEY_FILE"

systemctl daemon-reload
systemctl enable --now "$UNIT"
systemctl is-active --quiet "$UNIT" || { systemctl status --no-pager "$UNIT"; exit 1; }
echo "[ok] authenticated gateway listening on 0.0.0.0:8080 for $LAN_CIDR"
echo "[info] DS4 remains isolated on 127.0.0.1:8083"
