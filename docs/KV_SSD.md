# KV cache and SSD policy

## DS4 model
DS4 treats KV state as a first-class RAM/disk component for DeepSeek V4 Flash. That is the target concept.

Upstream DS4 has a real disk-KV design for its own engine. On Intel CPU this kit
does not pretend that `llama-server` exposes the same implementation. It provides
the closest stable operational substitute available in llama.cpp: server slots
and explicit slot save/restore on SSD.

## Intel 16 GB adaptation
With llama.cpp, use slot prompt cache persistence:
- Start server with `--slots`.
- Set `--slot-save-path /var/cache/local-ai/slots`.
- Prewarm long context.
- Save slot to SSD.
- Restore slot before related work.

This is not identical to DS4's disk KV engine. It is the reliable mechanism exposed by llama-server today.

## Commands
```bash
bash scripts/63_prewarm_from_file.sh docs/project-context.md project.bin
bash scripts/61_slot_restore.sh 0 project.bin
bash scripts/60_slot_save.sh 0 project.bin
```

Use SSD/NVMe. Avoid SD cards and cheap USB flash.

For the DS4 Intel profile, use `/var/cache/local-ai/ds4-slots` and keep one
active slot until benchmarks show the host can support parallel work.
