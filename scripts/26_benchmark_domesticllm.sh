#!/usr/bin/env bash
set -Eeuo pipefail

mode=${1:-quick}
case "$mode" in quick|full|ds4|ds4-dual|tune) ;; *) echo "usage: $0 [quick|full|ds4|ds4-dual|tune] [output-dir]" >&2; exit 2 ;; esac
output=${2:-"$PWD/domesticllm-benchmark-$(date -u +%Y%m%dT%H%M%SZ)"}
llama_bench=/opt/local-ai/llama-current/bin/llama-bench
ds4_bench=/opt/local-ai/current/bin/ds4-bench
model_dir=/opt/local-ai/models
lock="${XDG_RUNTIME_DIR:-/tmp}/domesticllm-console-${UID}.lock"

for command in flock nvidia-smi jq; do
  command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 1; }
done
for binary in "$llama_bench" "$ds4_bench"; do
  [ -x "$binary" ] || { echo "missing benchmark: $binary" >&2; exit 1; }
done
if pgrep -x llama-cli >/dev/null || pgrep -x ds4-agent >/dev/null; then
  echo "an inference process is active; benchmark aborted" >&2
  exit 1
fi
[ ! -e "$output" ] || { echo "output path already exists: $output" >&2; exit 1; }
mkdir -p "$output"
exec 9>"$lock"
flock -n 9 || { echo "DomesticLLM inference lock is busy" >&2; exit 1; }

capture_host() {
  {
    date -u +'%FT%TZ'
    uname -a
    lscpu
    free -b
    lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS
    nvidia-smi -q
    nvidia-smi topo -m
  } >"$output/host.txt"
}

run_llama() {
  local name=$1 file=$2 threads=$3 batch=$4 cache=$5
  local result="$output/llama-${name}-t${threads}-b${batch}-${cache}.json"
  local started finished
  echo "[bench] $name threads=$threads batch=$batch cache=$cache"
  started=$(date +%s)
  env LD_LIBRARY_PATH=/opt/local-ai/llama-current/lib CUDA_VISIBLE_DEVICES=0 \
    "$llama_bench" --model "$model_dir/$file" --offline --repetitions 3 \
      --n-prompt 512 --n-gen 128 --threads "$threads" --batch-size "$batch" \
      --ubatch-size 512 --cache-type-k "$cache" --cache-type-v "$cache" \
      --n-gpu-layers 999 --split-mode none --main-gpu 0 --output json \
      >"$result" 2>"${result%.json}.stderr.txt"
  finished=$(date +%s)
  printf 'started_epoch=%s\nfinished_epoch=%s\nelapsed_seconds=%s\n' \
    "$started" "$finished" "$((finished - started))" >"${result%.json}.time.txt"
  jq empty "$result"
}

run_ds4() {
  local cache_gb=$1
  local prompt="$output/ds4-prompt.txt"
  local started finished
  awk 'BEGIN { for (i=0; i<140; i++) print "DomesticLLM benchmark: measure deterministic local inference, cache behavior, tool steering, and stable shutdown." }' >"$prompt"
  echo "[bench] ds4 single GPU, SSD streaming, ${cache_gb} GiB expert cache"
  started=$(date +%s)
  env CUDA_VISIBLE_DEVICES=0 "$ds4_bench" --cuda \
      --model "$model_dir/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf" \
      --prompt-file "$prompt" --threads 16 --power 100 --ssd-streaming \
      --ssd-streaming-cache-experts "${cache_gb}GB" --prefill-chunk 2048 \
      --ctx-start 1024 --ctx-max 2048 --step-incr 1024 --gen-tokens 64 \
      --csv "$output/ds4-single-${cache_gb}gb.csv" 2>"$output/ds4-single-${cache_gb}gb.stderr.txt"
  finished=$(date +%s)
  printf 'started_epoch=%s\nfinished_epoch=%s\nelapsed_seconds=%s\n' \
    "$started" "$finished" "$((finished - started))" >"$output/ds4-single-${cache_gb}gb.time.txt"
}

run_ds4_dual() {
  local prompt="$output/ds4-prompt.txt"
  local started finished
  awk 'BEGIN { for (i=0; i<140; i++) print "DomesticLLM benchmark: measure deterministic local inference, cache behavior, tool steering, and stable shutdown." }' >"$prompt"
  echo "[bench] ds4 dual GPU tensor/expert parallel, SSD streaming, 6 GiB expert cache"
  started=$(date +%s)
  "$ds4_bench" --cuda --gpu-devices 0,1 --gpu-vram 18,18 --cuda-tensor-parallel \
    --model "$model_dir/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf" \
    --prompt-file "$prompt" --threads 16 --power 100 --ssd-streaming \
    --ssd-streaming-cache-experts 6GB --prefill-chunk 2048 \
    --ctx-start 1024 --ctx-max 2048 --step-incr 1024 --gen-tokens 64 \
    --csv "$output/ds4-dual-6gb.csv" 2>"$output/ds4-dual-6gb.stderr.txt"
  finished=$(date +%s)
  printf 'started_epoch=%s\nfinished_epoch=%s\nelapsed_seconds=%s\n' \
    "$started" "$finished" "$((finished - started))" >"$output/ds4-dual-6gb.time.txt"
}

capture_host
if [ "$mode" = quick ] || [ "$mode" = full ]; then
  run_llama cyber Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf 16 2048 q8_0
  run_llama qwen Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf 16 2048 q8_0
  run_llama mistral mistralai_Mistral-Small-3.1-24B-Instruct-2503-Q4_K_M.gguf 16 2048 q8_0
  run_llama dolphin cognitivecomputations_Dolphin3.0-Mistral-24B-Q4_K_M.gguf 16 2048 q8_0
fi
if [ "$mode" = full ] || [ "$mode" = tune ]; then
  for threads in 8 32; do
    run_llama cyber Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf "$threads" 2048 q8_0
  done
  run_llama cyber Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf 16 512 q8_0
  run_llama cyber Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf 16 2048 f16
fi
if [ "$mode" = ds4-dual ]; then
  run_ds4_dual
elif [ "$mode" != tune ]; then
  run_ds4 6
fi
if [ "$mode" = full ] || [ "$mode" = ds4 ]; then
  run_ds4 10
fi
echo "[ok] results: $output"
