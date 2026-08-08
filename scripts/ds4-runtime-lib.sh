#!/usr/bin/env bash

# Shared primitives for the native DS4 release scripts. Keep this file free of
# implicit network, sudo, service, and deletion operations.

ds4_die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

ds4_info() {
  printf '[info] %s\n' "$*" >&2
}

ds4_require_command() {
  command -v "$1" >/dev/null 2>&1 || ds4_die "required command not found: $1"
}

ds4_require_root() {
  [ "$(id -u)" -eq 0 ] || ds4_die "run this provisioning operation as root"
}

ds4_require_non_root() {
  [ "$(id -u)" -ne 0 ] || ds4_die "builds as root are forbidden; use an unprivileged build account"
}

ds4_valid_sha256() {
  case "$1" in
    *[!0-9a-f]*|'') return 1 ;;
  esac
  [ "${#1}" -eq 64 ]
}

ds4_kv_get() {
  local file="$1" key="$2" line value
  [ -r "$file" ] || ds4_die "cannot read configuration: $file"
  case "$key" in
    *[!A-Z0-9_]*|'') ds4_die "invalid configuration key: $key" ;;
  esac
  line="$(grep -E "^${key}=" "$file" || true)"
  [ -n "$line" ] || ds4_die "missing ${key} in $file"
  [ "$(printf '%s\n' "$line" | wc -l)" -eq 1 ] || ds4_die "duplicate ${key} in $file"
  value="${line#*=}"
  case "$value" in
    *$'\n'*|*$'\r'*) ds4_die "invalid newline in ${key}" ;;
  esac
  printf '%s\n' "$value"
}

ds4_verify_sha256() {
  local file="$1" expected="$2" actual
  ds4_valid_sha256 "$expected" || ds4_die "invalid SHA-256 for $file"
  [ -f "$file" ] || ds4_die "missing file: $file"
  actual="$(sha256sum "$file" | awk '{print $1}')"
  [ "$actual" = "$expected" ] || ds4_die "SHA-256 mismatch for $file: expected $expected, got $actual"
}

ds4_reject_partial_model() {
  case "$1" in
    *.bad|*.part|*.bad.*|*.part.*) ds4_die "quarantined or partial model cannot be used: $1" ;;
  esac
}

ds4_require_loopback() {
  case "$1" in
    127.0.0.1|::1|0.0.0.0) ;;
    *) ds4_die "native DS4 bind must be 127.0.0.1, ::1 or 0.0.0.0, got: $1" ;;
  esac
}

ds4_atomic_symlink() {
  local target="$1" link="$2" temporary
  temporary="${link}.new.$$"
  ln -s "$target" "$temporary"
  mv -Tf "$temporary" "$link"
}

ds4_set_env_key() {
  local file="$1" key="$2" value="$3" temporary
  [ -f "$file" ] || ds4_die "missing environment file: $file"
  case "$key" in
    *[!A-Z0-9_]*|'') ds4_die "invalid environment key: $key" ;;
  esac
  case "$value" in
    *[!A-Za-z0-9_.,:/+-]*|'') ds4_die "unsafe environment value for $key" ;;
  esac
  temporary="${file}.new.$$"
  awk -F= -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    $1 == key { print key "=" value; found = 1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$file" >"$temporary"
  chown --reference="$file" "$temporary"
  chmod --reference="$file" "$temporary"
  mv -f "$temporary" "$file"
}

ds4_http_ready() {
  local host="$1" port="$2" output probe_host
  ds4_require_loopback "$host"
  probe_host="$host"
  [ "$probe_host" = 0.0.0.0 ] && probe_host=127.0.0.1
  output="$(curl --fail --silent --show-error --max-time 10 \
    "http://${probe_host}:${port}/v1/models" 2>/dev/null)" || return 1
  printf '%s' "$output" | grep -Eq '"(data|id|object)"'
}

ds4_require_gate_file() {
  local file="$1" key value
  [ -f "$file" ] || ds4_die "acceptance evidence file not found: $file"
  [ ! -L "$file" ] || ds4_die "acceptance evidence must not be a symlink"
  [ -O "$file" ] || ds4_die "acceptance evidence must be owned by the invoking root account"
  [ -z "$(find "$file" -perm /022 -print -quit)" ] || ds4_die "acceptance evidence is group/world writable"
  for key in CORRECTNESS TOOL_CALLING DECODE_NOT_BELOW_BASELINE \
    TTFT_WITHIN_10_PERCENT GPU_ISOLATION STRESS_4H ROLLBACK_TESTED; do
    value="$(ds4_kv_get "$file" "$key")"
    [ "$value" = pass ] || ds4_die "promotion gate failed: ${key}=${value}"
  done
}
