# DomesticLLM performance profile

Validated on 2026-08-02 on the reference host: Ryzen 9 5950X, 128 GiB RAM,
NVMe, and two RTX A4500 20 GB GPUs. These values describe this workstation,
not a guarantee for other systems.

## Reproducible benchmark

```bash
scripts/26_benchmark_domesticllm.sh quick
scripts/26_benchmark_domesticllm.sh tune
scripts/26_benchmark_domesticllm.sh ds4
```

The harness refuses to run while an inference process or the DomesticLLM lock
is active. It runs one model at a time and writes host inventory, llama.cpp JSON,
DS4 CSV, stderr, and wall-clock timing to a timestamped output directory.

## Results

| Model | Prefill tok/s | Decode tok/s | Benchmark wall time |
|---|---:|---:|---:|
| Qwen3 Coder 30B-A3B | 2717 | 146.2 | 7 s |
| Dolphin3 Cyber 8B | 3343 | 90.1 | 6 s |
| Mistral Small 24B | 1169 | 32.2 | 19 s |
| Dolphin Mistral 24B | 1151 | 32.1 | 16 s |
| DeepSeek V4 Flash / DS4 | 57–65 | 1.75 | 108 s |

The wall times include model loading and three llama.cpp repetitions; DS4 used
two context frontiers and 64 generated tokens per frontier.

## Decisions supported by data

- Keep 16 CPU threads. Tests at 8, 16, and 32 were effectively identical.
- Keep batch 2048. Batch 512 did not produce a meaningful gain.
- Keep Q8 KV cache as the safe common default. F16 improved Cyber by about 3%
  but doubles KV memory and reduces the margin available to Qwen at long context.
- Keep the DS4 expert cache at 6 GiB. A 10 GiB cache consumed more VRAM without
  improving prefill or decode speed.
- Use Qwen for fast coding, Cyber for fast defensive-security work, and DS4 only
  when its larger model quality or native agent/KV features justify the latency.

## Dual-GPU DS4 result

The native balanced CUDA tensor/expert path was rejected before allocation on
this hardware. Auto budgets left 13.32 GiB usable per GPU; explicit 18/18 GiB
budgets left 15.18 GiB after reserves. Both were insufficient for balanced
stage 0 with 43 layers. No force-fit configuration is approved for production.

## CPU governor A/B result

A temporary `performance` run was compared with the `powersave` baseline and
the original governor was restored automatically afterward.

| Model | Prefill change | Decode change |
|---|---:|---:|
| Qwen3 Coder | +2.7% | +1.8% |
| Dolphin3 Cyber | +1.5% | +0.7% |
| Mistral Small | +2.3% | +0.7% |
| Dolphin Mistral | +2.7% | +0.7% |
| DeepSeek V4 Flash / DS4 | -0.4% to -0.7% | +0.6% |

These small GPU-bound gains do not justify permanently increasing workstation
power, heat, and noise. Keep `powersave` as the production default.
