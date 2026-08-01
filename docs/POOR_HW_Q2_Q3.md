# Poor-hardware q2/q3 lane

Operational assumption: storage is available, RAM/NVRAM are unknown, CPU is
Xeon-class, and the target follows the poor-hardware experiments where very low
quantization is preferred over pretending a large q4/q6 model is practical.

Policy:

- Default to q2.
- Treat q3 as the maximum normal quantization.
- Do not select q4/q5/q6 in installers or service profiles for this lane.
- Prefer sharded GGUF models where `llama.cpp` can load the first shard and find
  the rest in the same directory.
- Keep context and batch conservative until the actual host RAM is measured.

Current primary candidate:

- `unsloth/GLM-5.2-GGUF`
- Default variant: `UD-IQ2_XXS`
- Service profile: `conf/local-ai-glm52.env`

Download:

```bash
bash scripts/33_fetch_hf_gguf.sh glm-5.2 iq2_xxs
```

Escalation path after real RAM testing:

```bash
bash scripts/33_fetch_hf_gguf.sh glm-5.2 iq2_m
bash scripts/33_fetch_hf_gguf.sh glm-5.2 iq3_xxs
bash scripts/33_fetch_hf_gguf.sh glm-5.2 iq3_s
```

Rejected for this lane:

- `BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6`: upstream provides Q6_K only.
- Any q4/q5/q6 default profile.
