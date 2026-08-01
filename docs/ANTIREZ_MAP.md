# Antirez resource map

## linenoise
Use: local CLI REPL without GNU readline. Tiny dependency, history, line editing.

## sds
Use: dynamic strings inside C tools. Binary-safe strings with length metadata.

## kilo
Use: minimal local editor for prompt/config editing. Direct terminal workflow.

## ds4
Use as architectural reference for narrow native inference, API server for coding agents, KV state handling in RAM/on disk, CLI-first workflow, avoiding heavy frameworks. Build the locked CUDA runtime for production and retain `llama-server` as rollback.

PoorHW policy:
- CPU vendor/class is secondary: Intel Xeon/Core and AMD Ryzen/EPYC are accepted as CPU-only hosts.
- RAM is primary: 128 GiB means q2 imatrix; 256 GiB unlocks q4.
- Two mounted SATA disks are enough for this kit: one cache/slot path, one model path.
- Default topology is PowerShell agent on the laptop and Ubuntu inference server over Tailscale.

Upstream status to respect (locked 2026-07-28):
- primary ds4 backends are Metal, CUDA and ROCm;
- CPU path is reference/debug;
- CUDA SSD streaming permits a single dedicated 20 GiB GPU with an explicit expert-cache budget;
- `--power` is the preferred domestic heat/noise control;
- Responses, OpenAI chat and Anthropic messages endpoints are supported;
- DeepSeek V4 Flash GGUFs must be the DS4-published variants, not arbitrary GGUF files.

## gguf-tools
Use: inspect model metadata before deployment. Keep it out of the hot path.

## llama.cpp-deepseek-v4-flash
Use: reference branch to study DeepSeek V4 Flash support. For CPU serving, prefer current `ggml-org/llama.cpp` unless a specific regression requires this branch.

## botlib
Use: reference for small C network/agent style. Cloned and built opportunistically by `scripts/20_install_antirez_tools.sh`; not wired into the inference service because Telegram bot support is not part of the critical path.

## PixelWall
Use: optional status wall inspiration. Not part of critical inference path.

## qwen-asr
Use: optional local speech-to-text for voice notes / Telegram voice transcription.
