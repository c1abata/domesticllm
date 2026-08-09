#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
image="$(mktemp -d)"
fixtures="$(mktemp -d)"
cleanup() {
  chmod -R u+w "$image" "$fixtures" 2>/dev/null || true
  rm -rf -- "$image" "$fixtures"
}
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

ds4_fixture="$fixtures/ds4"
llama_fixture="$fixtures/876a4321163249c43ca4e986818fab5ab081f282"
install -d "$ds4_fixture/bin" "$llama_fixture/bin" "$llama_fixture/lib"
for binary in ds4 ds4-agent ds4-bench ds4-eval ds4-server; do
  install -m 0755 /bin/true "$ds4_fixture/bin/$binary"
done
install -m 0644 "$root/LICENSE" "$ds4_fixture/LICENSE"
printf '%s\n' 'BUILD_COMMIT=80df56af4070d0fc62f6f9682b1854f8e5be8b00' >"$ds4_fixture/build.env"
(
  cd "$ds4_fixture"
  find bin -type f -print | LC_ALL=C sort | xargs sha256sum
  sha256sum LICENSE build.env
) >"$ds4_fixture/manifest.sha256"
install -m 0755 /bin/true "$llama_fixture/bin/llama-server"
install -m 0644 /bin/true "$llama_fixture/lib/libllama-test.so"
PDS4_DESTDIR="$image" PDS4_VERSION=runtime-test \
  PDS4_DS4_RUNTIME="$ds4_fixture" PDS4_LLAMA_RUNTIME="$llama_fixture" \
  "$root/scripts/pds4-install"
[ -x "$image/opt/pds4/releases/runtime-test/bin/ds4-server" ]
[ -x "$image/opt/pds4/releases/runtime-test/bin/llama-server" ]
[ -f "$image/opt/pds4/releases/runtime-test/lib/libllama-test.so" ]
[ -f "$image/opt/pds4/releases/runtime-test/runtime.sha256" ]

printf '%s\n' 'BUILD_COMMIT=0000000000000000000000000000000000000000' >"$ds4_fixture/build.env"
(
  cd "$ds4_fixture"
  find bin -type f -print | LC_ALL=C sort | xargs sha256sum
  sha256sum LICENSE build.env
) >"$ds4_fixture/manifest.sha256"
if PDS4_DESTDIR="$image" PDS4_VERSION=wrong-runtime \
  PDS4_DS4_RUNTIME="$ds4_fixture" "$root/scripts/pds4-install" >/dev/null 2>&1; then
  echo "installer accepted a DS4 runtime from the wrong commit" >&2
  exit 1
fi
if rg -n '(curl|wget|git clone|pip install|apt-get)' "$root/systemd"/pds4-* "$root/build"; then
  echo "network-capable command found in build or startup path" >&2
  exit 1
fi
echo "[ok] offline image install and startup policy"
