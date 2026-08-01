#!/usr/bin/env bash
set -euo pipefail
LOCAL_AI_HOME="${LOCAL_AI_HOME:-/opt/local-ai}"
REPOS="$LOCAL_AI_HOME/repos"
SRC="$LOCAL_AI_HOME/src/localai-repl"
[ "$(id -u)" -eq 0 ] || { echo "Run as root; compilation is delegated to localai-build" >&2; exit 1; }
id localai-build >/dev/null 2>&1 || { echo "Missing build user localai-build" >&2; exit 1; }
install -d -o localai-build -g localai-build -m 0750 "$SRC"
install -o localai-build -g localai-build -m 0644 src/localai-repl.c "$SRC/"
install -o localai-build -g localai-build -m 0644 \
  "$REPOS/linenoise/linenoise.c" "$REPOS/linenoise/linenoise.h" \
  "$REPOS/sds/sds.c" "$REPOS/sds/sds.h" "$SRC/"
if [ -f "$REPOS/sds/sdsalloc.h" ]; then
  install -o localai-build -g localai-build -m 0644 "$REPOS/sds/sdsalloc.h" "$SRC/"
fi
runuser -u localai-build -- cc -O2 -Wall -Wextra -Werror \
  "$SRC/localai-repl.c" "$SRC/linenoise.c" "$SRC/sds.c" \
  -lcurl -o "$SRC/localai-repl"
install -o root -g root -m 0755 "$SRC/localai-repl" "$LOCAL_AI_HOME/bin/localai-repl"
echo "[ok] localai-repl built"
