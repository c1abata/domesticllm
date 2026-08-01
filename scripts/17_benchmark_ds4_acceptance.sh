#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/ds4-runtime-lib.sh
. "$ROOT/scripts/ds4-runtime-lib.sh"

BACKEND=""
PROMPT_FILE=""
OUTPUT_DIR=""
API_KEY_FILE=""
PORT=""
MODEL="deepseek-v4-flash"

usage() {
  cat <<'EOF'
Usage: scripts/17_benchmark_ds4_acceptance.sh --backend ds4|llama \
  --prompt-file FILE --output-dir DIR [--api-key-file FILE] [--port N]

Runs one backend only. Stop the other huge-model service before invoking it.
The request is identical for both backends and raw evidence is kept mode 0600.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backend) BACKEND="${2:?missing backend}"; shift 2 ;;
    --prompt-file) PROMPT_FILE="${2:?missing prompt file}"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:?missing output directory}"; shift 2 ;;
    --api-key-file) API_KEY_FILE="${2:?missing API key file}"; shift 2 ;;
    --port) PORT="${2:?missing port}"; shift 2 ;;
    --model) MODEL="${2:?missing model}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) ds4_die "unknown option: $1" ;;
  esac
done

case "$BACKEND" in
  ds4) : "${PORT:=8083}"; unit=local-ai-ds4-native.service ;;
  llama) : "${PORT:=8082}"; unit=local-ai-ds4-nvidia.service ;;
  *) ds4_die "--backend must be ds4 or llama" ;;
esac
[ -f "$PROMPT_FILE" ] || ds4_die "prompt file not found: $PROMPT_FILE"
[ -n "$OUTPUT_DIR" ] || ds4_die "--output-dir is required"
for command in python3 systemctl ps nvidia-smi install find; do
  ds4_require_command "$command"
done
systemctl is-active --quiet "$unit" || ds4_die "benchmark unit is not active: $unit"

install -d -m 0700 "$OUTPUT_DIR"
request="$OUTPUT_DIR/request.json"
response="$OUTPUT_DIR/response.sse"
http_metrics="$OUTPUT_DIR/http-metrics.json"
sampler_pid=""

cleanup() {
  if [ -n "$sampler_pid" ]; then
    kill "$sampler_pid" >/dev/null 2>&1 || true
    wait "$sampler_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

PROMPT_FILE="$PROMPT_FILE" REQUEST_FILE="$request" MODEL="$MODEL" python3 - <<'PY'
import json
import os

with open(os.environ["PROMPT_FILE"], "r", encoding="utf-8") as source:
    prompt = source.read()
request = {
    "model": os.environ["MODEL"],
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0,
    "max_tokens": 256,
    "stream": True,
    "stream_options": {"include_usage": True},
}
with open(os.environ["REQUEST_FILE"], "w", encoding="utf-8") as target:
    json.dump(request, target, ensure_ascii=False)
PY

if [ -n "$API_KEY_FILE" ]; then
  [ -f "$API_KEY_FILE" ] || ds4_die "API key file not found"
  [ ! -L "$API_KEY_FILE" ] || ds4_die "API key file must not be a symlink"
  [ -z "$(find "$API_KEY_FILE" -perm /037 -print -quit)" ] || ds4_die "API key file must be mode 0640 or stricter"
fi

pid="$(systemctl show --property MainPID --value "$unit")"
ps -o pid=,rss=,vsz=,etime= -p "$pid" >"$OUTPUT_DIR/process-before.txt"
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu,power.draw \
  --format=csv,noheader,nounits >"$OUTPUT_DIR/gpu-before.csv"
nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used,temperature.gpu,power.draw \
  --format=csv,noheader,nounits --loop-ms=500 >"$OUTPUT_DIR/gpu-samples.csv" &
sampler_pid=$!
REQUEST_FILE="$request" RESPONSE_FILE="$response" METRICS_FILE="$http_metrics" \
  API_KEY_FILE="$API_KEY_FILE" PORT="$PORT" python3 - <<'PY'
import http.client
import json
import os
import time

with open(os.environ["REQUEST_FILE"], "rb") as source:
    body = source.read()
headers = {"Content-Type": "application/json"}
key_file = os.environ.get("API_KEY_FILE")
if key_file:
    with open(key_file, "r", encoding="utf-8") as source:
        key = source.read().strip()
    if not key:
        raise SystemExit("empty API key file")
    headers["Authorization"] = "Bearer " + key

connection = http.client.HTTPConnection("127.0.0.1", int(os.environ["PORT"]), timeout=1800)
started = time.monotonic()
connection.request("POST", "/v1/chat/completions", body=body, headers=headers)
reply = connection.getresponse()
headers_at = time.monotonic()
if reply.status < 200 or reply.status >= 300:
    error = reply.read(4096).decode("utf-8", "replace")
    raise SystemExit(f"HTTP {reply.status}: {error}")

first_token_at = None
usage = {}
events = 0
with open(os.environ["RESPONSE_FILE"], "wb") as raw:
    while True:
        line = reply.readline()
        if not line:
            break
        raw.write(line)
        if not line.startswith(b"data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == b"[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if event.get("usage"):
            usage = event["usage"]
        choices = event.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            if delta.get("content") or delta.get("reasoning_content") or delta.get("tool_calls"):
                events += 1
                if first_token_at is None:
                    first_token_at = time.monotonic()

finished = time.monotonic()
connection.close()
if first_token_at is None:
    raise SystemExit("stream contained no completion or tool-call event")

ttft = first_token_at - started
decode_seconds = max(finished - first_token_at, 0.0)
prompt_tokens = usage.get("prompt_tokens")
completion_tokens = usage.get("completion_tokens")
metrics = {
    "http_code": reply.status,
    "headers_seconds": headers_at - started,
    "ttft_seconds": ttft,
    "total_seconds": finished - started,
    "decode_seconds": decode_seconds,
    "stream_events": events,
    "prompt_tokens": prompt_tokens,
    "completion_tokens": completion_tokens,
    "prefill_tokens_per_second_proxy": (
        prompt_tokens / ttft if isinstance(prompt_tokens, int) and ttft > 0 else None
    ),
    "decode_tokens_per_second": (
        completion_tokens / decode_seconds
        if isinstance(completion_tokens, int) and decode_seconds > 0
        else None
    ),
}
with open(os.environ["METRICS_FILE"], "w", encoding="utf-8") as target:
    json.dump(metrics, target, indent=2, sort_keys=True)
    target.write("\n")
PY
kill "$sampler_pid" >/dev/null 2>&1 || true
wait "$sampler_pid" 2>/dev/null || true
sampler_pid=""
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu,power.draw \
  --format=csv,noheader,nounits >"$OUTPUT_DIR/gpu-after.csv"
ps -o pid=,rss=,vsz=,etime= -p "$pid" >"$OUTPUT_DIR/process-after.txt"
systemctl show "$unit" --property ActiveState,SubState,MainPID,MemoryCurrent,MemoryPeak >"$OUTPUT_DIR/unit.txt"

GPU_SAMPLES="$OUTPUT_DIR/gpu-samples.csv" GPU_SUMMARY="$OUTPUT_DIR/gpu-summary.json" \
  BACKEND="$BACKEND" python3 - <<'PY'
import csv
import json
import os

maximum = {}
with open(os.environ["GPU_SAMPLES"], newline="", encoding="utf-8") as source:
    for row in csv.reader(source):
        if len(row) < 6:
            continue
        try:
            index = int(row[1].strip())
            utilization = float(row[2].strip())
        except ValueError:
            continue
        maximum[index] = max(maximum.get(index, 0.0), utilization)

summary = {"maximum_gpu_utilization_percent": maximum}
with open(os.environ["GPU_SUMMARY"], "w", encoding="utf-8") as target:
    json.dump(summary, target, indent=2, sort_keys=True)
    target.write("\n")
if os.environ["BACKEND"] == "ds4":
    if maximum.get(0, 0.0) <= 0:
        raise SystemExit("DS4 GPU isolation gate failed: GPU 0 showed no activity")
    if maximum.get(1, 0.0) > 0:
        raise SystemExit("DS4 GPU isolation gate failed: reserved GPU 1 showed activity")
PY

python3 -m json.tool "$http_metrics" >/dev/null || ds4_die "invalid benchmark metrics"
ds4_info "benchmark evidence written to $OUTPUT_DIR"
