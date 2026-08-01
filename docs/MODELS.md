# Model policy

Poor-hardware experimental lane: use q2 first and q3 as the hard ceiling.
Treat q4/q5/q6 as legacy, small-model fallback, or explicit workstation/server
experiments only.

| Use | Model class | Quant |
|---|---|---|
| coding legacy | Qwen2.5-Coder 7B Instruct GGUF | Q4_K_M, not poor-HW lane |
| coding light legacy | Qwen2.5-Coder 3B | Q5/Q6, not poor-HW lane |
| general legacy | Qwen2.5 7B Instruct GGUF | Q4_K_M, not poor-HW lane |
| fast fallback legacy | Phi-3.5-mini | Q4/Q5, not poor-HW lane |
| DwarfStar4 Intel, 128 GB | DeepSeek V4 Flash GGUF for DS4 | q2 imatrix |
| DwarfStar4 Intel, 160 GB | DeepSeek V4 Flash GGUF for DS4 | mixed q2/q4 imatrix, not poor-HW lane |
| DwarfStar4 Intel, 256 GB+ | DeepSeek V4 Flash GGUF for DS4 | q4 imatrix, not poor-HW lane |
| DwarfStar4 Intel, 512 GB+ | DeepSeek V4 PRO GGUF for DS4 | q2 imatrix, experimental |
| cyber/security research | BugTraceAI CORE-Ultra 27B GGUF | Q6_K only in provided repo; not poor-HW default |
| frontier long-horizon/coding | GLM-5.2 GGUF | UD-IQ2_XXS default, UD-IQ3_XXS/UD-IQ3_S if RAM allows |

Avoid on 16 GB: DeepSeek V4 Flash as production; 30B/70B dense models; large multimodal models.

Default DS4 choice: `scripts/90_install_ds4_intel_stack.sh --variant auto`.

Optional controlled-use model for the 128 GiB profile:

- `uncensored-q2`: Huihui DeepSeek V4 Flash abliterated Q2, 86.7 GB. It is
  locked independently and linked as `ds4flash-uncensored.gguf`; it never
  replaces the official `ds4flash.gguf` baseline. Abliterated weights reduce
  refusals but provide no accuracy, legality or safety guarantee. Keep the
  endpoint loopback-only and evaluate tool calling before agent use.

After the normal network/download human gate:

```bash
sudo MODEL_DIR=/opt/local-ai/models \
  bash scripts/32_fetch_ds4_flash_gguf.sh uncensored-q2
```
It selects only Flash variants (`q2`, `q2q4-mixed`, `q4`) from host RAM and
refuses small machines unless `--force` is used for diagnostics. `pro-q2` is
explicit only.

DS4 GGUF filenames supported by the helper script:

- `q2`: `DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf`
- `q2q4-mixed`: `DeepSeek-V4-Flash-Layers37-42Q4KExperts-OtherExpertLayersIQ2XXSGateUp-Q2KDown-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix-fixed.gguf`
- `q4`: `DeepSeek-V4-Flash-Q4KExperts-F16HC-F16Compressor-F16Indexer-Q8Attn-Q8Shared-Q8Out-chat-v2-imatrix.gguf`
- `mtp`: `DeepSeek-V4-Flash-MTP-Q4K-Q8_0-F32.gguf`
- `pro-q2`: `DeepSeek-V4-Pro-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-Instruct-imatrix.gguf`

Additional HF GGUF fetcher:

```bash
# Repo-local copies, default destination: ./models.
# For this poor-hardware profile prefer 2-bit first, 3-bit only if RAM allows.
bash scripts/33_fetch_hf_gguf.sh glm-5.2 iq2_xxs
bash scripts/33_fetch_hf_gguf.sh glm-5.2 iq3_xxs

# Deploy-ready copy under /opt/local-ai/models
sudo MODEL_DIR=/opt/local-ai/models bash scripts/33_fetch_hf_gguf.sh glm-5.2 iq2_xxs
```

BugTraceAI uses a single Q6 GGUF in the requested repository:

- `BugTraceAI-CORE-Ultra-SFT-Q6_K.gguf`

That quantization is refused by default by `scripts/33_fetch_hf_gguf.sh`, because
this lane is capped at q2/q3. Use `ALLOW_OVER_Q3=1` only for a deliberate
workstation/server experiment.

GLM-5.2 is sharded. For `llama.cpp`, point `LOCAL_AI_MODEL` to the first shard
and keep all shards in the same quant directory:

- `UD-IQ2_XXS/GLM-5.2-UD-IQ2_XXS-00001-of-00006.gguf`

Supported GLM 2/3-bit variants in `scripts/33_fetch_hf_gguf.sh`:

- `iq2_xxs`: default 2-bit candidate, 6 shards
- `iq2_m`: stronger 2-bit candidate, 6 shards
- `iq3_xxs`: smallest 3-bit candidate, 7 shards
- `iq3_s`: stronger 3-bit candidate, 8 shards
- `q3_k_m`: 3-bit K-quant candidate, 9 shards

Profiles:

- `conf/local-ai-glm52.env`
