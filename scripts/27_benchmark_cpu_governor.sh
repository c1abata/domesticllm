#!/usr/bin/env bash
set -Eeuo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
benchmark=/tmp/26_benchmark_domesticllm.sh
[ -x "$benchmark" ] || { echo "missing benchmark: $benchmark" >&2; exit 1; }

operator=${SUDO_USER:-ale}
operator_uid=$(id -u "$operator")
operator_home=$(getent passwd "$operator" | cut -d: -f6)
if [ -z "$operator_home" ] || [ ! -d "$operator_home" ]; then
  echo "invalid operator home" >&2
  exit 1
fi

mapfile -t policies < <(find /sys/devices/system/cpu/cpufreq -mindepth 2 -maxdepth 2 \
  -type f -name scaling_governor -print | sort)
((${#policies[@]} > 0)) || { echo "no CPU frequency policies found" >&2; exit 1; }

state=$(mktemp)
restore() {
  local path governor
  while IFS=$'\t' read -r path governor; do
    if [ -w "$path" ]; then
      printf '%s' "$governor" >"$path" || true
    fi
  done <"$state"
  rm -f -- "$state"
}
trap restore EXIT HUP INT TERM

for path in "${policies[@]}"; do
  available=${path%/*}/scaling_available_governors
  grep -qw performance "$available" || { echo "performance governor unavailable: $path" >&2; exit 1; }
  printf '%s\t%s\n' "$path" "$(<"$path")" >>"$state"
done
for path in "${policies[@]}"; do
  printf performance >"$path"
done

output="$operator_home/domesticllm-benchmarks/cpu-performance-$(date -u +%Y%m%dT%H%M%SZ)"
echo "[cpu] governor=performance operator=$operator output=$output"
runuser -u "$operator" -- env XDG_RUNTIME_DIR="/run/user/$operator_uid" \
  "$benchmark" quick "$output"
echo "[ok] CPU governor restored on exit; results: $output"
