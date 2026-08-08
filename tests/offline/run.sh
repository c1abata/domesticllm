#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
image="$(mktemp -d)"
cleanup() { chmod -R u+w "$image" 2>/dev/null || true; rm -rf -- "$image"; }
trap cleanup EXIT
PDS4_DESTDIR="$image" PDS4_VERSION=offline-test "$root/scripts/pds4-install"
[ "$(readlink "$image/opt/pds4/current")" = /opt/pds4/releases/offline-test ]
[ -x "$image/opt/pds4/releases/offline-test/bin/pds4" ]
[ -x "$image/opt/pds4/releases/offline-test/bin/pds4-gateway" ]
[ -f "$image/etc/pds4/models.d/flash-q2.json" ]
[ -f "$image/etc/systemd/system/pds4-flash.service" ]
[ -f "$image/etc/systemd/system/pds4-fast@.service" ]
[ -f "$image/etc/systemd/system/pds4-gateway.service" ]
[ -f "$image/etc/pds4/gateway.key" ]
if rg -n '(curl|wget|git clone|pip install|apt-get)' "$root/systemd"/pds4-* "$root/build"; then
  echo "network-capable command found in build or startup path" >&2
  exit 1
fi
echo "[ok] offline image install and startup policy"
