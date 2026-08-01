# DwarfStar4 on Intel/AMD CPU

Questa guida e' deliberatamente stretta: un server Ubuntu, CPU Intel/AMD, molta
RAM, un solo servizio di inferenza, una sola API, un profilo agent pronto.
Niente framework pesanti nel percorso critico.

## Verita' operativa

Upstream `antirez/ds4` e' un motore nativo per DeepSeek V4 Flash/PRO. Non e' un
runner GGUF generico. I backend pratici sono Metal, CUDA e ROCm; il build CPU
serve soprattutto per diagnostica, verifica tokenizer/modello e sviluppo.

Su Intel/AMD CPU il percorso stabile e' quindi:

- GGUF DeepSeek V4 Flash/PRO pubblicati per DS4.
- `llama-server` come motore OpenAI-compatible.
- Systemd separato: `local-ai-ds4-intel`.
- Cache/slot su SSD come adattamento pragmatico dell'idea DS4 di KV come stato
  persistente.
- `ds4`, `ds4-server`, `ds4-agent` compilati solo come riferimento diagnostico,
  non come servizio CPU principale.

## Modello scelto

Default per questo kit: DeepSeek V4 Flash q2 imatrix con 128 GiB RAM. La classe
CPU conta meno della RAM: Xeon/Core/Ryzen/EPYC entry-level vanno trattati come
nodi CPU-only lenti ma usabili per agenti pazienti.

| RAM host | Variante | Uso |
|---|---|---|
| < 112 GiB | nessuna | Non usare DS4 Flash; resta su 3B/7B. |
| 112/128 GiB | `q2` | Default consigliato. |
| 160 GiB | `q2q4-mixed` | Qualita' migliore, piu' memoria. |
| 256 GiB+ | `q4` | Profilo piu' solido se la RAM basta. |
| 512 GiB+ | `pro-q2` | Sperimentale, non default agent. |

La scelta automatica dello script usa solo Flash (`q2`, `q2q4-mixed`, `q4`).
`pro-q2` va richiesto esplicitamente. Sotto soglia fallisce prima di scaricare
decine di GB, a meno di usare `--force` per diagnostica.

## Installazione professionale

Sul server Ubuntu 24.04 LTS:

```bash
git clone <questo-repo>
cd local-ai-antirez-full-poorhw-kit
sudo bash scripts/90_install_ds4_intel_stack.sh --variant q2 \
  --tailnet-client-ip TAILNET_CLIENT_IP \
  --cache-dir /mnt/sata-cache/local-ai/ds4-slots \
  --models-dir /mnt/sata-models/local-ai/models
```

Lo script fa tutto il percorso ripetibile:

- installa dipendenze base e utente `localai`;
- prepara Ubuntu Server 24.04/26.04, path cache e path modelli;
- compila `llama.cpp` CPU con OpenBLAS e native CPU flags;
- clona i repository antirez utili;
- compila `ds4` CPU reference, salvo `--skip-ds4-reference`;
- sceglie o scarica il GGUF DS4;
- genera una API key se `LOCAL_AI_API_KEY` non e presente nell'ambiente;
- scrive `/etc/local-ai-ds4-intel.env`;
- installa e avvia `local-ai-ds4-intel.service`;
- opzionalmente apre UFW solo verso il CIDR LAN indicato;
- controlla `/health`;
- installa `/usr/local/bin/local-ai` come CLI/TUI operativa.

Esempi:

```bash
sudo bash scripts/90_install_ds4_intel_stack.sh --variant q2 --tailnet-client-ip 100.64.1.25
sudo bash scripts/90_install_ds4_intel_stack.sh --variant q2 --cache-dir /mnt/sata-cache/local-ai/ds4-slots --models-dir /mnt/sata-models/local-ai/models
sudo bash scripts/90_install_ds4_intel_stack.sh --variant auto --skip-download
```

## Installazione manuale

Usala solo se devi debuggare un passaggio.

```bash
sudo bash scripts/00_install_base.sh
sudo bash scripts/10_install_llamacpp_cpu.sh
sudo bash scripts/20_install_antirez_tools.sh
sudo bash scripts/11_install_ds4_cpu_reference.sh
sudo bash scripts/32_fetch_ds4_flash_gguf.sh q2
sudo cp conf/local-ai-ds4-intel.env /etc/local-ai-ds4-intel.env
sudo cp systemd/local-ai-ds4-intel.service /etc/systemd/system/
sudo install -d -o localai -g localai -m 750 /var/cache/local-ai/ds4-slots
sudo systemctl daemon-reload
sudo systemctl enable --now local-ai-ds4-intel
```

Varianti supportate:

```bash
sudo bash scripts/32_fetch_ds4_flash_gguf.sh q2
sudo bash scripts/32_fetch_ds4_flash_gguf.sh q2q4-mixed
sudo bash scripts/32_fetch_ds4_flash_gguf.sh q4
sudo bash scripts/32_fetch_ds4_flash_gguf.sh mtp
sudo bash scripts/32_fetch_ds4_flash_gguf.sh pro-q2
```

## Verifica

```bash
curl http://127.0.0.1:8081/health
ENV_FILE=/etc/local-ai-ds4-intel.env bash scripts/50_ask.sh "Rispondi solo OK"
ENV_FILE=/etc/local-ai-ds4-intel.env SERVICE=local-ai-ds4-intel bash scripts/80_health_report.sh
local-ai status
local-ai ask "Rispondi solo OK"
```

Chat completions diretta:

```bash
LOCAL_AI_API_KEY="$(cat /etc/local-ai-ds4-intel.key)"
export LOCAL_AI_API_KEY
curl http://127.0.0.1:8081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${LOCAL_AI_API_KEY}" \
  -d '{"model":"ds4flash","messages":[{"role":"user","content":"Rispondi solo OK"}],"max_tokens":8}'
```

## DS4 come agent

Sul client dove usi opencode:

```bash
mkdir -p ~/.config/opencode/agents
cp opencode/opencode.ds4-intel-lan.json ~/.config/opencode/opencode.json
cp agents/*.md ~/.config/opencode/agents/
```

Mantieni i riferimenti all'ambiente:

```json
"baseURL": "{env:LOCAL_AI_BASE_URL}",
"apiKey": "{env:LOCAL_AI_API_KEY}"
```

Profilo operativo:

- `plan-local`: lettura, grep, glob, list. Nessuna scrittura.
- `build-local`: patch piccole, tool con conferma.
- context 8192, output 1536: abbastanza per agenti lenti e affidabili.
- niente repo enormi in contesto; escludi binari, virtualenv, GGUF e database.

### Agent su PowerShell, inferenza sul server

Sul laptop Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local-ai-client.ps1 `
  -ConfigureOpenCode
```

Test:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local-ai-client.ps1 `
  -Prompt 'Rispondi solo OK'
```

## Tuning

Lo script scrive parametri conservativi. Per 128/160 GiB usa cache KV `q4_0`;
per 256 GiB+ usa `q8_0`.

Se vedi swap o OOM:

```env
LOCAL_AI_CTX=4096
LOCAL_AI_BATCH=64
LOCAL_AI_UBATCH=16
LOCAL_AI_CACHE_TYPE_K=q4_0
LOCAL_AI_CACHE_TYPE_V=q4_0
LOCAL_AI_PARALLEL=1
```

Se la macchina resta stabile per ore:

```env
LOCAL_AI_CTX=16384
LOCAL_AI_BATCH=256
LOCAL_AI_UBATCH=64
```

Riavvia sempre dopo modifiche:

```bash
sudo systemctl restart local-ai-ds4-intel
journalctl -u local-ai-ds4-intel -f
```

## Diagnostica minima

```bash
systemctl status local-ai-ds4-intel --no-pager
journalctl -u local-ai-ds4-intel -n 100 --no-pager
free -h
ss -lntp | grep ':8081'
du -h /var/cache/local-ai/ds4-slots
```

Se `llama-server` non parte, controlla in ordine:

1. `/opt/local-ai/models/ds4flash.gguf` esiste ed e' un symlink valido.
2. `/etc/local-ai-ds4-intel.env` non contiene API key vuota.
3. RAM libera sufficiente per la variante scelta.
4. `/var/cache/local-ai/ds4-slots` e' scrivibile da `localai`.
5. La porta 8081 non e' gia' occupata.

## Cosa non promette

- Non rende `ds4` CPU un motore production.
- Non supporta GGUF arbitrari dentro `ds4`.
- Non rende DeepSeek V4 Flash sensato su 16 GiB.
- Non espone la LAN senza API key e firewall esplicito.
