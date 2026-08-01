# Local model copy

- Source: https://huggingface.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6
- Variant: Q6_K
- Primary file for llama.cpp: BugTraceAI-CORE-Ultra-SFT-Q6_K.gguf
- Downloaded with: scripts/33_fetch_hf_gguf.sh

For sharded GGUF models, point `LOCAL_AI_MODEL` to the first shard and keep all
other shards in the same directory.
