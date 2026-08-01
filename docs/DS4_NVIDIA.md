# DwarfStar4 on Ryzen 9 5950X + NVIDIA RTX A4500

Profilo per Asus ProArt X570-Creator/Ace class, Ryzen 9 5950X, 128 GiB RAM,
NVMe, due NVIDIA RTX A4500 o GPU Ampere simili.

## Verita' operativa

La macchina ha molta RAM e due GPU buone, ma DeepSeek V4 Flash resta un modello
RAM-heavy. Le due A4500 accelerano una parte dei layer; non trasformano 40 GiB
di VRAM in un full-offload del modello q2/q4.

Percorso stabile domesticLLM del kit:

- `llama-server` compilato CUDA come servizio OpenAI-compatible.
- GGUF ufficiali `antirez/deepseek-v4-gguf`.
- Build nativa `antirez/ds4` CUDA bloccata come riferimento; sulle 2xA4500 non
  viene avviata perché il GGUF q2 non entra nella VRAM aggregata.
- Slot/KV cache su NVMe.
- Servizio separato: `local-ai-ds4-nvidia` su porta `8082`.

## Prerequisiti duri

Prima dello script il driver NVIDIA e il CUDA Toolkit devono gia' essere sani:

```bash
nvidia-smi
nvcc --version
```

Per RTX A4500 class usa compute capability `86`: lo script passa
`-DCMAKE_CUDA_ARCHITECTURES=86` a `llama.cpp` e `CUDA_ARCH=sm_86` al build
nativo `ds4`.

## Installazione end-to-end

```bash
sudo bash scripts/90_install_ds4_nvidia_stack.sh --variant q2 \
  --tailnet-client-ip TAILNET_CLIENT_IP \
  --cache-dir /mnt/nvme/local-ai/ds4-slots \
  --models-dir /mnt/nvme/local-ai/models
```

Lo script:

- verifica RAM, `nvidia-smi`, `nvcc` e VRAM visibile;
- prepara utente, directory, sysctl e pacchetti base;
- compila `llama.cpp` con CUDA;
- clona tool antirez e compila `gguf-tools` dove possibile;
- compila `antirez/ds4` con target CUDA generico, salvo `--skip-ds4-reference`;
- scarica il GGUF DS4 scelto;
- scrive `/etc/local-ai-ds4-nvidia.env`;
- installa `local-ai-ds4-nvidia.service`;
- attende `/health`.

## Parametri iniziali

Default per questa macchina:

```env
LOCAL_AI_PORT=8082
LOCAL_AI_CTX=8192
LOCAL_AI_BATCH=256
LOCAL_AI_UBATCH=64
LOCAL_AI_N_GPU_LAYERS=16
LOCAL_AI_SPLIT_MODE=layer
CUDA_VISIBLE_DEVICES=0,1
CUDA_SCALE_LAUNCH_QUEUES=4x
GGML_CUDA_ENABLE_UNIFIED_MEMORY=0
GGML_CUDA_P2P=0
```

`LOCAL_AI_N_GPU_LAYERS=16` e' volutamente conservativo per due A4500 da 20 GiB.
Se il servizio resta stabile e la VRAM libera e' ampia, prova 20, 24, 28. Se
va in OOM, torna a 12 o 8.

## Verifica

```bash
curl http://127.0.0.1:8082/health
ENV_FILE=/etc/local-ai-ds4-nvidia.env SERVICE=local-ai-ds4-nvidia local-ai status
ENV_FILE=/etc/local-ai-ds4-nvidia.env bash scripts/50_ask.sh "Rispondi solo OK"
journalctl -u local-ai-ds4-nvidia -n 100 --no-pager
nvidia-smi
```

Benchmark minimo:

```bash
/opt/local-ai/bin/llama-bench \
  -m /opt/local-ai/models/ds4flash.gguf \
  -ngl 16 \
  -p 512 \
  -n 64
```

## Tuning

Se vedi OOM o reset CUDA:

```env
LOCAL_AI_N_GPU_LAYERS=8
LOCAL_AI_BATCH=128
LOCAL_AI_UBATCH=32
GGML_CUDA_P2P=0
```

Se la macchina e' stabile:

```env
LOCAL_AI_N_GPU_LAYERS=20
LOCAL_AI_BATCH=384
LOCAL_AI_UBATCH=96
```

Riavvia sempre:

```bash
sudo systemctl restart local-ai-ds4-nvidia
```

Abilita `GGML_CUDA_P2P=1` solo dopo aver verificato che la topologia PCIe lo
supporti bene:

```bash
nvidia-smi topo -m
```

Su alcune motherboard/IOMMU il peer access e' una fonte di crash o output
sospetti; per questo il kit lo lascia spento.

## DS4 nativo sulle due A4500

Il build nativo installa, quando presenti:

```bash
/opt/local-ai/bin/ds4
/opt/local-ai/bin/ds4-server
/opt/local-ai/bin/ds4-bench
/opt/local-ai/bin/ds4-agent
```

Il runtime bloccato supporta CUDA SSD streaming. Il profilo validato dedica
GPU0 a DS4, mantiene 4 GB di esperti caldi in VRAM e lascia GPU1 libera:

```bash
cd /opt/local-ai/repos/ds4
CUDA_VISIBLE_DEVICES=0 ./ds4 -m /opt/local-ai/models/ds4flash-uncensored.gguf --cuda \
  --ssd-streaming --ssd-streaming-cache-experts 4GB --power 100 \
  -p "Rispondi solo OK"
./ds4-server --help
```

`llama-server` resta il percorso di fallback installato e testato.

## Cosa non promette

- Non installa automaticamente driver NVIDIA o CUDA Toolkit.
- Non forza full-offload su 40 GiB VRAM.
- Non abilita P2P di default.
- Non espone il servizio senza API key e firewall esplicito.
