# Unified LAN inference gateway

The gateway is the only LAN listener: `http://0.0.0.0:8080`. The web interface
at `/` has no authentication by operator request. All `/v1/*` API endpoints
require `Authorization: Bearer <token>`; retrieve that token only on the host
with `scripts/show-api-token.sh`. Restrict TCP/8080 to the trusted LAN at the
host firewall. The underlying `llama-server` and native DS4 processes bind
only to loopback and are switched serially, so model changes release the prior
model’s CPU RAM and GPU allocations first.

The catalog contains at most three already-installed GGUFs:

- `dolphin-8b-q4`: fast abliterated Dolphin profile on GPU 0;
- `qwen3-coder-30b-ud-q4`: coding profile split over both RTX A4500 GPUs;
- `deepseek-v4-flash-iq2`: native DS4 profile with two-GPU tensor parallelism,
  SSD expert streaming, warm weights, disk KV, and conservative context.

The DeepSeek Q2 profile is retained for a larger-GPU host but is not admitted
on this server. A native DS4 CUDA baseline with SSD streaming, cold cache,
8 GiB expert cache, and both A4500s failed at placement: the remaining balanced
stage exceeds the effective 14.16 GiB per-GPU budget. Requests receive HTTP
409 instead of entering a failing load path.

Use the web interface to select models, system prompt, temperature, top-p,
top-k, min-p, seed, repeat/presence/frequency penalties, stop sequences,
maximum tokens, context, slot count, Flash Attention mode and KV cache type.
The same page shows live session status: active model, session elapsed time,
request count, and measured prefill and generation throughput from the latest
completed non-streaming response.
Authenticated API clients use `/v1/models` and `/v1/host/status`; standard
OpenAI chat/completions/responses requests select the profile in `model`.
Streaming responses are relayed.
