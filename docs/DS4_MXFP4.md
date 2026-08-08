# DS4 `ds4f-mxfp4` assessment

Review date: 2026-08-08. Requested branch head:
`80df56af4070d0fc62f6f9682b1854f8e5be8b00`.

This is a canary input, not an automatic production promotion. It is 19 commits
ahead of the previously validated DomesticLLM revision
`54b36ed9ba42da31b24f2d1a5feb075c2475dbb1`.

## Relevant upstream changes

- common DeepSeek decode/prefill work, including indexed attention, routed MoE
  dispatch compaction, Q-head normalization/RoPE fusion and Q8 tile alignment;
- correctness fixes for dense Q4 dispatch and imatrix delimiter parsing;
- lossless conversion of DeepSeek V4 Flash 0731 MXFP4 weights to GGUF;
- a scalar MXFP4 reference and portable Metal MXFP4 expert inference;
- refreshed 0731 official-quality fixtures;
- hot streamed-expert cache seeding from mapped prefill layers.

DomesticLLM adopts the exact source pin and adds upstream's
`mxfp4-dot-test` to the offline model-independent build gate. The existing
canary/acceptance/rollback path remains mandatory because the target hardware
has not run this revision yet.

## Decision for the two RTX A4500 GPUs

Do not deploy MXFP4 weights on this CUDA workstation at this revision. The
branch adds scalar and Metal MXFP4 execution, but no CUDA MXFP4 kernel. A format
converter and a passing scalar dot product do not make the model executable or
fast on NVIDIA.

The working model remains the locked q2-imatrix GGUF:

```text
DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf
SHA-256 a02f4e9ed0f7cd4d51b79ccb21e72a9fd17b5104a14361c9a333798d4e6ea5c8
size 86,720,111,488 bytes
```

The model is called “2 bit” because the routed MoE experts dominate its size:
their gate/up tensors use `IQ2_XXS` and down tensors use `Q2_K`. Shared experts,
attention projections, routing and output tensors remain at higher precision to
protect quality. Prefer imatrix-tuned weights; do not turn every tensor into a
uniform 2-bit quant.

Requirements for the q2 path:

- at least 112 GiB usable system RAM, 128 GiB recommended;
- the exact locked single-file GGUF and verified SHA-256;
- fast NVMe for the GGUF and KV directory;
- explicit `sm_86` build, never `native`;
- one A4500 assigned to DS4 with the 6 GiB expert-cache budget, GPU1 reserved
  for the resident fast lane;
- 100k context only after the existing memory/correctness acceptance passes.

The q2/q4 hybrid improves the final six expert layers but is a 150+ GiB class
profile in this stack. It is not appropriate for the 128 GiB target. Full q4 is
a 256 GiB class profile.

## Performance and concurrency

`ds4-server --batched-session N` owns `N` resident KV states. Native CUDA
batching is designed for supported multi-GPU tensor/expert-parallel layouts;
single-GPU CUDA uses an exact ordered fallback. Upstream states that two GPUs do
not have enough VRAM for its DeepSeek tensor-parallel layout, so DomesticLLM
keeps one A4500 on the SSD-streaming capacity lane and defaults to one 100k
session.

Test `DS4_BATCHED_SESSIONS=2` only as a separate canary. It passes only if:

1. both concurrent answers are correct and isolated;
2. RSS/VRAM stay below the recorded safety ceiling;
3. TTFT fairness improves without unacceptable single-request regression;
4. four-hour mixed chat/tool/KV soak succeeds;
5. rollback restores the previous one-session release.

DSpark/MTP speculation is also excluded from the default: upstream describes it
as experimental and at most a slight gain, and it is disabled when native
session batching is active. Measure it later with greedy coding prompts and a
separate locked support GGUF.

## Target release gate

Run, in order, on the workstation:

```bash
scripts/14_build_ds4_native.sh --source /path/to/exact-ds4-checkout
sudo scripts/15_install_ds4_native.sh --artifact artifacts/ds4-80df56af4070d0fc62f6f9682b1854f8e5be8b00 --start-canary
sudo scripts/16_ds4_health.sh health
sudo scripts/17_benchmark_ds4_acceptance.sh
```

Then run the four-hour soak and rollback drill documented in
`docs/DS4_RUNTIME.md`. Do not promote merely because the repository tests pass.
