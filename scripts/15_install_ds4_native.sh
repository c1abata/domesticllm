#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/ds4-runtime-lib.sh
. "$ROOT/scripts/ds4-runtime-lib.sh"

LOCK_FILE="$ROOT/conf/ds4-runtime.lock"
ENV_TEMPLATE="$ROOT/conf/ds4-runtime-a4500.env"
ENV_DST="${DS4_ENV_FILE:-/etc/local-ai-ds4-runtime.env}"
ARTIFACT=""
START_CANARY=0

usage() {
  cat <<'EOF'
Usage: sudo scripts/15_install_ds4_native.sh --artifact DIR [--start-canary]

Installs an already-built, verified artifact. It never downloads a model,
driver, CUDA toolkit, source tree, or package.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --artifact) ARTIFACT="${2:?missing artifact directory}"; shift 2 ;;
    --start-canary) START_CANARY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) ds4_die "unknown option: $1" ;;
  esac
done

[ -n "$ARTIFACT" ] || ds4_die "--artifact is required"
ds4_require_root
for command in install sha256sum systemctl readlink find; do
  ds4_require_command "$command"
done

commit="$(ds4_kv_get "$LOCK_FILE" DS4_COMMIT)"
[ "$(ds4_kv_get "$ARTIFACT/build.env" BUILD_COMMIT)" = "$commit" ] || ds4_die "artifact commit is not locked DS4 commit"
[ "$(ds4_kv_get "$ARTIFACT/build.env" BUILD_TARGET)" = cuda ] || ds4_die "artifact is not a CUDA build"
[ "$(ds4_kv_get "$ARTIFACT/build.env" BUILD_CUDA_ARCH)" = sm_86 ] || ds4_die "artifact is not built for sm_86"
(
  cd "$ARTIFACT"
  sha256sum --check --strict manifest.sha256
)

model="$(ds4_kv_get "$ENV_TEMPLATE" DS4_MODEL)"
model_sha="$(ds4_kv_get "$ENV_TEMPLATE" DS4_MODEL_SHA256)"
[ "$model_sha" = "$(ds4_kv_get "$LOCK_FILE" MODEL_SHA256)" ] || ds4_die "runtime model hash differs from lock"
[ "$(basename "$model")" = "$(ds4_kv_get "$LOCK_FILE" MODEL_FILENAME)" ] || ds4_die "runtime model filename differs from lock"
ds4_reject_partial_model "$model"
ds4_verify_sha256 "$model" "$model_sha"

release_root="$(ds4_kv_get "$ENV_TEMPLATE" DS4_RELEASES_DIR)"
current_link="$(ds4_kv_get "$ENV_TEMPLATE" DS4_CURRENT)"
previous_link="$(ds4_kv_get "$ENV_TEMPLATE" DS4_PREVIOUS)"
release="$release_root/$commit"
temporary="${release}.install.$$"
home="$(ds4_kv_get "$ENV_TEMPLATE" DS4_HOME)"
model_dir="$(dirname "$model")"

id localai >/dev/null 2>&1 || ds4_die "service account localai is missing; run the base provisioning first"
install -d -o root -g root -m 0755 "$home"
if [ ! -d "$model_dir" ]; then
  install -d -o root -g root -m 0755 "$model_dir"
fi
model_dir="$(readlink -f "$model_dir")"
chown root:root "$home" "$model_dir"
chmod 0755 "$home" "$model_dir"
install -d -o root -g root -m 0555 "$release_root"
if [ ! -d "$release" ]; then
  trap 'if [ -n "${temporary:-}" ] && [ -d "$temporary" ]; then rm -rf -- "$temporary"; fi' EXIT
  install -d -o root -g root -m 0555 "$temporary/bin"
  for binary in ds4 ds4-server ds4-agent ds4-bench ds4-eval; do
    install -o root -g root -m 0555 "$ARTIFACT/bin/$binary" "$temporary/bin/$binary"
  done
  install -o root -g root -m 0444 "$ARTIFACT/LICENSE" "$ARTIFACT/build.env" \
    "$ARTIFACT/manifest.sha256" "$temporary/"
  (
    cd "$temporary"
    sha256sum --check --strict manifest.sha256
  )
  chmod 0555 "$temporary"
  mv "$temporary" "$release"
  temporary=""
  trap - EXIT
else
  (
    cd "$release"
    sha256sum --check --strict manifest.sha256
  )
fi

old_current=""
if [ -L "$current_link" ]; then
  old_current="$(readlink -f "$current_link")"
fi
if [ -n "$old_current" ] && [ "$old_current" != "$release" ]; then
  ds4_atomic_symlink "$old_current" "$previous_link"
fi
ds4_atomic_symlink "$release" "$current_link"

chown root:localai "$model"
chmod 0440 "$model"
install -d -o localai -g localai -m 0750 /var/cache/local-ai/ds4/kv /var/log/local-ai
install -o root -g localai -m 0640 "$ENV_TEMPLATE" "$ENV_DST"
install -d -o root -g root -m 0755 \
  /usr/local/libexec/local-ai/scripts \
  /usr/local/libexec/local-ai/conf \
  /usr/local/libexec/local-ai/systemd \
  /usr/local/libexec/local-ai/opencode \
  /usr/local/libexec/local-ai/agents
if [ "$ROOT" != /usr/local/libexec/local-ai ]; then
  install -o root -g root -m 0444 \
    "$ROOT/scripts/ds4-runtime-lib.sh" \
    /usr/local/libexec/local-ai/scripts/ds4-runtime-lib.sh
  for helper in 15_install_ds4_native.sh 16_ds4_health.sh \
    17_benchmark_ds4_acceptance.sh 18_promote_ds4_native.sh \
    19_rollback_llama.sh 50_ask.sh client-auth.sh local-ai.sh; do
    install -o root -g root -m 0555 "$ROOT/scripts/$helper" \
      "/usr/local/libexec/local-ai/scripts/$helper"
  done
  install -o root -g root -m 0444 \
    "$ROOT/conf/ds4-runtime.lock" \
    "$ROOT/conf/ds4-runtime-a4500.env" \
    /usr/local/libexec/local-ai/conf/
  install -o root -g root -m 0444 \
    "$ROOT/systemd/local-ai-ds4-native.service" \
    "$ROOT/systemd/local-ai-llama-fallback.service" \
    /usr/local/libexec/local-ai/systemd/
  install -o root -g root -m 0444 "$ROOT"/opencode/*.json \
    /usr/local/libexec/local-ai/opencode/
  install -o root -g root -m 0444 "$ROOT"/agents/*.md \
    /usr/local/libexec/local-ai/agents/
fi
install -o root -g root -m 0555 "$ROOT/scripts/16_ds4_health.sh" /usr/local/libexec/local-ai/ds4-health
install -o root -g root -m 0555 "$ROOT/scripts/domesticllm-tui.py" /usr/local/bin/domesticllm-tui
install -o root -g root -m 0555 "$ROOT/scripts/local-ai.sh" /usr/local/bin/local-ai
install -o root -g root -m 0444 "$ROOT/systemd/local-ai-ds4-native.service" /etc/systemd/system/local-ai-ds4-native.service
install -o root -g root -m 0444 "$ROOT/systemd/local-ai-llama-fallback.service" /etc/systemd/system/local-ai-llama-fallback.service
systemctl daemon-reload

if [ "$START_CANARY" -eq 1 ]; then
  [ "$(ds4_kv_get "$ENV_DST" DS4_PORT)" = "$(ds4_kv_get "$ENV_DST" DS4_CANARY_PORT)" ] || ds4_die "refusing canary start on a non-canary port"
  if ! systemctl enable --now local-ai-ds4-native.service; then
    systemctl disable --now local-ai-ds4-native.service >/dev/null 2>&1 || true
    ds4_die "canary failed to start and was disabled"
  fi
  if ! /usr/local/libexec/local-ai/ds4-health wait; then
    systemctl disable --now local-ai-ds4-native.service >/dev/null 2>&1 || true
    ds4_die "canary health failed and was disabled"
  fi
fi

ds4_info "installed native DS4 release $commit"
ds4_info "current release: $current_link -> $release"
