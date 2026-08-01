#!/usr/bin/env bash
set -euo pipefail

VENDOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../conf/vendor-refs.env
. "$VENDOR_ROOT/conf/vendor-refs.env"

LOCAL_AI_HOME="${LOCAL_AI_HOME:-/opt/local-ai}"
LOCAL_AI_BUILD_USER="${LOCAL_AI_BUILD_USER:-localai-build}"
REPOS="${REPOS:-$LOCAL_AI_HOME/repos}"

require_root() {
  [ "$(id -u)" -eq 0 ] || {
    echo "Run as root for installation: sudo bash $0" >&2
    exit 1
  }
}

validate_commit() {
  case "$1" in
    (*[!0-9a-f]*|'') echo "Invalid locked commit: $1" >&2; exit 1 ;;
  esac
  [ "${#1}" -eq 40 ] || { echo "Locked commit must be 40 hex chars" >&2; exit 1; }
}

prepare_build_dirs() {
  require_root
  id -u "$LOCAL_AI_BUILD_USER" >/dev/null 2>&1 || {
    echo "Missing build user: $LOCAL_AI_BUILD_USER (run scripts/00_install_base.sh)" >&2
    exit 1
  }
  install -d -o "$LOCAL_AI_BUILD_USER" -g "$LOCAL_AI_BUILD_USER" -m 0750 "$REPOS"
  install -d -o root -g root -m 0755 "$LOCAL_AI_HOME/bin"
}

checkout_locked_repo() {
  local name="$1" url="$2" commit="$3"
  local repo="$REPOS/$name"
  validate_commit "$commit"
  if [ ! -d "$repo/.git" ]; then
    install -d -o "$LOCAL_AI_BUILD_USER" -g "$LOCAL_AI_BUILD_USER" -m 0750 "$repo"
    runuser -u "$LOCAL_AI_BUILD_USER" -- git -C "$repo" init
    runuser -u "$LOCAL_AI_BUILD_USER" -- git -C "$repo" remote add origin "$url"
  else
    runuser -u "$LOCAL_AI_BUILD_USER" -- git -C "$repo" remote set-url origin "$url"
  fi
  [ -z "$(git -C "$repo" status --porcelain --untracked-files=all --ignored=matching)" ] || {
    echo "Refusing dirty vendor checkout: $repo" >&2
    exit 1
  }
  runuser -u "$LOCAL_AI_BUILD_USER" -- git -C "$repo" fetch --depth 1 origin "$commit"
  runuser -u "$LOCAL_AI_BUILD_USER" -- git -C "$repo" checkout --detach FETCH_HEAD
  local actual
  actual="$(git -C "$repo" rev-parse HEAD)"
  [ "$actual" = "$commit" ] || {
    echo "Locked checkout mismatch for $name: $actual != $commit" >&2
    exit 1
  }
}

run_build() {
  runuser -u "$LOCAL_AI_BUILD_USER" -- "$@"
}
