# CLI/TUI operations

Obiettivo: un solo comando per installare, verificare e usare il profilo locale
su hardware non premium.

## Server Ubuntu scelto

Default: Ubuntu Server 24.04 LTS. Ubuntu Server 26.04 LTS e' supportato se
serve kernel piu' nuovo, ma per un nodo headless stabile il profilo base resta
24.04 LTS.

Hardware target:

- CPU Intel/AMD qualunque di classe power user o entry-level server.
- RAM ipotizzata: 128 GiB.
- Dischi: almeno 2 SATA da 256 GB gia' montati.
- Topologia: agente PowerShell sul laptop, inferenza sul server via Tailscale.

Installazione DS4 Intel/AMD CPU profile:

```bash
sudo bash scripts/90_install_ds4_intel_stack.sh --variant q2 \
  --tailnet-client-ip TAILNET_CLIENT_IP \
  --cache-dir /mnt/sata-cache/local-ai/ds4-slots \
  --models-dir /mnt/sata-models/local-ai/models
```

Se i dischi non sono ancora montati, montarli prima in modo persistente via
`/etc/fstab`. Questo kit non formatta dischi: evita distruzioni accidentali.

Dopo l'installazione:

```bash
local-ai tui
local-ai status
local-ai ask "Rispondi solo OK"
local-ai logs
local-ai restart
local-ai decision
```

Per DS4 nativo usare la TUI streaming, che resta visibile anche durante il
prefill e segnala un possibile stallo senza terminare un'elaborazione lenta:

```bash
domesticllm-tui "Spiega una skip list"
```

La schermata mostra fase (`CONNESSIONE`, `IN CODA / PREFILL`, `GENERAZIONE`),
tempo dall'ultimo evento, TTFT, occupazione stimata
del contesto, token prompt/cache/output e velocita' di decode. Le soglie sono
configurabili con `DOMESTICLLM_SLOW_SECONDS` (45 secondi) e
`DOMESTICLLM_STALL_SECONDS` (600 secondi, per non confondere il thinking lungo
di DS4 con uno stallo). In pipe o senza terminale interattivo
il comando emette heartbeat testuali su stderr e la risposta pulita su stdout.

Nel profilo LAN autorizzato, il gateway autenticato ascolta su `0.0.0.0:8080`
ma accetta traffico solamente dal CIDR fornito all'installer; DS4 resta su
loopback. Configurare il client senza inserire la chiave negli argomenti:

```bash
export DOMESTICLLM_URL=http://SERVER_LAN_IP:8080/v1/chat/completions
export LOCAL_AI_API_KEY_FILE="$HOME/.config/domesticllm/lan.key"
domesticllm-tui "Descrivi lo stato del sistema"
```

Sul client configurato in questo scenario basta:

```bash
domesticllm-lan "Descrivi lo stato del sistema"
```

`domesticllm-lan` legge l'host da `DOMESTICLLM_LAN_HOST` oppure dalla prima
riga di `~/.config/domesticllm/lan.host`.

Il comando `local-ai` legge di default:

```bash
/etc/local-ai-ds4-intel.env
```

Per un env diverso:

```bash
ENV_FILE=/etc/local-ai.env SERVICE=local-ai-cpu local-ai status
```

## Client Linux via tailnet

Sul client:

```bash
export LOCAL_AI_BASE_URL=http://127.0.0.1:8083/v1
export LOCAL_AI_API_KEY="$(cat /percorso/protetto/local-ai.key)"
local-ai opencode-config
```

Oppure manuale:

```bash
mkdir -p ~/.config/opencode/agents
cp opencode/opencode.ds4-intel-lan.json ~/.config/opencode/opencode.json
cp agents/*.md ~/.config/opencode/agents/
```

`baseURL` e `apiKey` restano rispettivamente `{env:LOCAL_AI_BASE_URL}` e
`{env:LOCAL_AI_API_KEY}`. Il client usa il loopback di un tunnel autorizzato;
endpoint e segreto non vengono salvati nel JSON.

## Client PowerShell via tailnet

Solo agente sul laptop Windows, inferenza sul server:

```powershell
$secret = Read-Host "LOCAL_AI_API_KEY" -AsSecureString
$env:LOCAL_AI_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
$env:LOCAL_AI_BASE_URL = "http://127.0.0.1:8083/v1"
powershell -ExecutionPolicy Bypass -File .\scripts\local-ai-client.ps1 `
  -ConfigureOpenCode
```

La chiave non deve essere passata come argomento: finirebbe nella command line
del processo. Il client accetta solo URL assoluti `http`/`https`, senza
credenziali, query o fragment.

Test diretto:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local-ai-client.ps1 `
  -BaseUrl http://127.0.0.1:8083/v1 `
  -Prompt 'Rispondi solo OK'
```

## Decision gate

Decisione corrente:

- CPU: non discriminante tra Xeon/Core/Ryzen/EPYC se restiamo CPU-only.
- RAM: 128 GiB -> `q2` imatrix.
- Cache: disco SATA dedicato, path passato con `--cache-dir`.
- Modelli: secondo disco SATA, path passato con `--models-dir`.
- Rete: Tailscale, IP client passato con `--tailnet-client-ip`.
- Agente: PowerShell sul laptop, server Ubuntu per inferenza.

Linea dura:

- sotto 112 GiB RAM non usare DS4 Flash;
- `ds4` CPU nativo resta build diagnostico;
- servizio stabile su Intel/AMD CPU: `llama-server` + GGUF DS4;
- SSD usato per slot/cache, non come scusa per RAM insufficiente.
