# Build order
1. Ubuntu Server prep: OS check, packages, localai user, cache/model dirs.
2. llama.cpp CPU.
3. Antirez tools.
4. Model link.
5. Systemd service.
6. Firewall tailnet/LAN.
7. PowerShell or opencode client.
8. Optional: local REPL.
9. Optional: qwen-asr.


## DwarfStar4 Intel CPU profile

Recommended for 128 GiB RAM, two mounted SATA disks, PowerShell agent:

```bash
sudo bash scripts/90_install_ds4_intel_stack.sh --variant q2 \
  --tailnet-client-ip TAILNET_CLIENT_IP \
  --cache-dir /mnt/sata-cache/local-ai/ds4-slots \
  --models-dir /mnt/sata-models/local-ai/models
```

Manual order:

1. Ubuntu Server prep: `scripts/05_prepare_ubuntu_server.sh`.
2. llama.cpp CPU.
3. Antirez tools.
4. Optional DS4 CPU reference build.
5. Download one DeepSeek V4 Flash GGUF.
6. Install `local-ai-ds4-intel.service`.
7. Install CLI/TUI launcher as `/usr/local/bin/local-ai`.
8. Verify health and one chat completion on port 8081.
9. Configure opencode or PowerShell client over tailnet.

Operator commands:

```bash
local-ai tui
local-ai status
local-ai ask "Rispondi solo OK"
local-ai decision
```


## DwarfStar4 NVIDIA CUDA profile

Recommended for Ryzen 9 5950X, 128 GiB RAM, NVMe, and two RTX A4500-class GPUs:

```bash
sudo bash scripts/90_install_ds4_nvidia_stack.sh --variant q2 \
  --tailnet-client-ip TAILNET_CLIENT_IP \
  --cache-dir /mnt/nvme/local-ai/ds4-slots \
  --models-dir /mnt/nvme/local-ai/models
```

Manual order:

1. Validate NVIDIA driver and CUDA Toolkit: `nvidia-smi`, `nvcc --version`.
2. Ubuntu Server prep: `scripts/05_prepare_ubuntu_server.sh`.
3. llama.cpp CUDA: `scripts/12_install_llamacpp_cuda.sh`.
4. Antirez tools: `scripts/20_install_antirez_tools.sh`.
5. Optional native DS4 CUDA reference: `scripts/13_install_ds4_cuda_reference.sh`.
6. Download one DeepSeek V4 Flash GGUF.
7. Install `local-ai-ds4-nvidia.service`.
8. Verify health and one chat completion on port 8082.

Operator commands:

```bash
ENV_FILE=/etc/local-ai-ds4-nvidia.env SERVICE=local-ai-ds4-nvidia local-ai status
ENV_FILE=/etc/local-ai-ds4-nvidia.env SERVICE=local-ai-ds4-nvidia local-ai ask "Rispondi solo OK"
```
