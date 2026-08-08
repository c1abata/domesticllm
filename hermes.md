
# Decisione architetturale
voglio realizzare e rendere disponibile la possibilità di inferenza per tutti i modelli del server ad un hermes agent installato su wsl che usa il server per risolvere i task.

> Stato verificato il 2026-08-08. Il percorso implementato usa un solo gateway
> DomesticLLM autenticato: aggrega i modelli realmente attivi, instrada DS4 e la
> fast lane e resta raggiungibile da WSL tramite tunnel SSH. Gli esempi pronti
> all'uso sono in `examples/hermes/`; `scripts/28_configure_hermes_wsl.sh`
> installa soltanto la configurazione locale, senza scaricare software o avviare
> servizi.

Pensa così:

* **Hermes Agent = caposquadra sul laptop**
* **DwarfStar con i modelli disponibili sul server = motore d’inferenza sul server**
* **Tailscale + tunnel SSH = collegamento privato**
* **File, Git e terminale restano sul laptop**
* **RAM e GPU del modello restano sul server**

Non devi installare DwarfStar in WSL per collegarlo al DwarfStar remoto. Il `ds4-agent` nativo incorpora direttamente il motore d’inferenza e non è attualmente progettato come client sottile verso un server remoto; la separazione client/server stateful è indicata upstream come sviluppo futuro. Per il caso “cervello remoto, mani locali” la soluzione corretta è **Hermes locale collegato a `ds4-server` tramite API OpenAI-compatible**. ([GitHub][1])

```text
┌──────────────────── LAPTOP WINDOWS ────────────────────┐
│                                                       │
│  WSL2 Ubuntu                                          │
│  ┌─────────────────────────────────────────────────┐  │
│  │ Hermes Agent                                    │  │
│  │                                                 │  │
│  │ terminal backend: local                         │  │
│  │ cwd: repository sul laptop                      │  │
│  │ strumenti: git, shell, file, ricerca, patch     │  │
│  └──────────────────────┬──────────────────────────┘  │
│                         │                              │
│              http://127.0.0.1:18080/v1                │
│                         │                              │
│              tunnel SSH dentro Tailscale              │
└─────────────────────────┼──────────────────────────────┘
                          │
┌─────────────────────────┼──── SERVER DOMESTICLLM ──────┐
│                         ▼                              │
│              127.0.0.1:8080 (gateway autenticato)     │
│                                                       │
│  DomesticLLM                                          │
│  ┌─────────────────────────────────────────────────┐  │
│  │ Runtime attivo                                  │  │
│  │                                                 │  │
│  │ DS4 :8083 / DeepSeek V4 Flash                   │  │
│  │ llama.cpp :8085 / profilo fast attivo           │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
│  GGUF, KV cache, GPU, RAM, NVMe restano sul server    │
└───────────────────────────────────────────────────────┘
```

DomesticLLM è già costruito secondo questo principio: DwarfStar per DeepSeek V4 Flash, `llama.cpp` per gli altri modelli e un’unica console che evita di avviare contemporaneamente due processi molto pesanti.

---

# Quali modelli puoi usare realmente con Hermes

Qui è necessario distinguere tra **modello che genera testo** e **modello adatto a pilotare un agente con strumenti**.

| Modello DomesticLLM               |        Hermes Agent | Situazione attuale                                                 |
| --------------------------------- | ------------------: | ------------------------------------------------------------------ |
| **DeepSeek V4 Flash tramite DS4** |              **Sì** | Scelta corretta e già validata per tool calling e contesto 100k    |
| **Qwen3-Coder 30B canary**        |               si    | Il profilo documentato parte da 16k; Hermes richiede almeno 64k    |
| **Dolphin**                       |         Solo chat | Non concedere strumenti: contesto 16k e profilo non validato       |
| **Cyber / BugTraceAI**            |          Non ancora | Profilo di ricerca; tool calling e contesto devono essere validati |
| **GLM 5.2**                       | Possibile in futuro | Solo dopo test completi di serving, contesto e tool calling        |

La documentazione DomesticLLM definisce al momento **native DS4 Flash come unico backend agentico**. Il Qwen canary parte da 16k di contesto e Dolphin è dichiarato non idoneo come backend per agenti.

Hermes rifiuta per uso agentico modelli con meno di 64.000 token di contesto, perché prompt di sistema, schemi degli strumenti e cronologia consumano molto spazio. ([GitHub][2])

## Conseguenza pratica

Per la prima installazione professionale:

```text
Hermes → gateway DomesticLLM → DS4 / DeepSeek V4 Flash
```

Non configurare subito Dolphin o Cyber come agenti. Potrai usarli successivamente come endpoint di chat specialistici, ma non concedere loro accesso al terminale o ai file finché non superano:

1. contesto effettivo di almeno 64k;
2. test di tool calling;
3. test multi-turno;
4. test di modifica file;
5. test di rollback;
6. test contro prompt injection.

---

# 1. Verifica del server DomesticLLM

Collegati al server e posizionati nel repository:

```bash
cd /percorso/domesticllm
```

Controlla i servizi esistenti:

```bash
systemctl list-units --type=service --all 'local-ai*'
```

Controlla le porte:

```bash
sudo ss -ltnp | grep -E ':(8080|8082|8083|8084|8085)\b'
```

La configurazione documentata usa:

* `8080`: gateway autenticato e Web UI;
* `8082`: backend promosso/stabile;
* `8083`: DS4 canary;
* `8084`: fallback `llama.cpp` avviato manualmente.
* `8085`: fast lane `llama.cpp`, un profilo alla volta.

DS4 deve restare associato a `127.0.0.1`, perché non dispone di autenticazione nativa da considerare una barriera di sicurezza. DomesticLLM raccomanda esplicitamente tunnel SSH o accesso controllato attraverso la tailnet.

Verifica il backend stabile:

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:8082/v1/models | jq
```

L’output deve contenere un modello simile a:

```json
{
  "id": "deepseek-v4-flash"
}
```

Test minimo:

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [
      {
        "role": "user",
        "content": "Rispondi esclusivamente con: DOMESTICLLM_OK"
      }
    ],
    "stream": false,
    "max_tokens": 32
  }' | jq
```

Puoi inoltre utilizzare il controllo previsto dal repository:

```bash
sudo scripts/16_ds4_health.sh health
```

## Console unificata DomesticLLM

Per controllare quale profilo è disponibile:

```bash
ds4
```

Dentro la console:

```text
/models
/status
```

Per scegliere e avviare un modello:

```text
/model NOME_ESATTO
/run
/status
```

Usa sempre il nome restituito da `/models`; non indovinare nomi o alias.

---

# 2. Configurazione Tailscale e WSL2

## Scelta raccomandata

Esegui Tailscale su **Windows**, non contemporaneamente anche dentro WSL.

La documentazione Tailscale sconsiglia di eseguire Tailscale sia sul sistema Windows sia dentro WSL2, perché il doppio incapsulamento può provocare problemi di MTU e connettività. ([Tailscale][3])

## Controllo iniziale da WSL

```bash
getent hosts NOME-SERVER-TAILSCALE
```

Poi:

```bash
ssh UTENTE_SERVER@NOME-SERVER-TAILSCALE
```

Quando MagicDNS non viene risolto, prova temporaneamente l’indirizzo Tailscale `100.x.y.z`.

## Modalità di rete WSL consigliata

Su Windows 11 recente, la modalità mirrored migliora la compatibilità con VPN e permette a Windows e WSL di condividere meglio la connettività. ([Microsoft Learn][4])

In PowerShell:

```powershell
notepad "$env:USERPROFILE\.wslconfig"
```

Inserisci:

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
firewall=true
```

Applica:

```powershell
wsl --shutdown
```

Riapri WSL e ripeti:

```bash
getent hosts NOME-SERVER-TAILSCALE
ssh UTENTE_SERVER@NOME-SERVER-TAILSCALE
```

---

# 3. Preparazione di WSL

Dentro Ubuntu WSL:

```bash
sudo apt update
sudo apt install -y \
  ca-certificates \
  curl \
  git \
  jq \
  openssh-client \
  ripgrep
```

Crea una directory Linux per i repository:

```bash
mkdir -p ~/src
chmod 700 ~/src
```

Per i progetti su cui deve lavorare Hermes, preferisci:

```text
/home/tuo-utente/src/progetto
```

invece di lavorare direttamente dentro:

```text
/mnt/c/...
```

In questo modo Git, permessi Unix e strumenti CLI operano nello stesso ambiente in cui gira Hermes.

---

# 4. Chiave SSH dedicata

Genera una chiave separata per DomesticLLM:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh

ssh-keygen \
  -t ed25519 \
  -a 64 \
  -f ~/.ssh/id_ed25519_domesticllm \
  -C "wsl-hermes-domesticllm"
```

Installa la chiave sul server:

```bash
ssh-copy-id \
  -i ~/.ssh/id_ed25519_domesticllm.pub \
  UTENTE_SERVER@NOME-SERVER-TAILSCALE
```

Crea la configurazione SSH:

```bash
nano ~/.ssh/config
```

Inserisci:

```sshconfig
Host domesticllm
    HostName NOME-SERVER-TAILSCALE
    User UTENTE_SERVER
    IdentityFile ~/.ssh/id_ed25519_domesticllm
    IdentitiesOnly yes

    ServerAliveInterval 30
    ServerAliveCountMax 3
    TCPKeepAlive yes

    ExitOnForwardFailure yes

    LocalForward 127.0.0.1:18080 127.0.0.1:8080
```

Proteggi il file:

```bash
chmod 600 ~/.ssh/config
chmod 600 ~/.ssh/id_ed25519_domesticllm
```

---

# 5. Avvio del tunnel

Avvia il tunnel da WSL:

```bash
ssh -NT domesticllm
```

Questa finestra deve restare aperta.

In un secondo terminale WSL verifica:

```bash
printf 'header = "Authorization: Bearer %s"\n' "$DOMESTICLLM_API_KEY" | \
  curl --config - --fail --silent --show-error \
  http://127.0.0.1:18080/v1/models | jq
```

Poi:

```bash
printf 'header = "Authorization: Bearer %s"\n' "$DOMESTICLLM_API_KEY" | \
  curl --config - --fail --silent --show-error \
  http://127.0.0.1:18080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [
      {
        "role": "user",
        "content": "Rispondi esclusivamente con TUNNEL_OK"
      }
    ],
    "max_tokens": 32,
    "stream": false
  }' | jq
```

Il percorso finale è:

```text
Hermes
  → 127.0.0.1:18080
  → SSH dentro Tailscale
  → server 127.0.0.1:8080
  → gateway → DS4 :8083 oppure fast lane :8085
```

Nessuna porta del modello viene pubblicata in LAN o direttamente sulla tailnet.

---

# 6. Installazione controllata di Hermes Agent

L’installer ufficiale supporta Linux e WSL2. ([GitHub][5])

Scarica prima lo script, senza eseguirlo immediatamente:

```bash
curl --fail --silent --show-error \
  https://hermes-agent.nousresearch.com/install.sh \
  -o /tmp/hermes-install.sh
```

Controllalo:

```bash
less /tmp/hermes-install.sh
```

Poi eseguilo:

```bash
bash /tmp/hermes-install.sh
```

Ricarica la shell:

```bash
source ~/.bashrc
```

Verifica:

```bash
hermes --version
hermes doctor
hermes dump
```

---

# 7. Crea un profilo Hermes dedicato

Non mescolare questa configurazione con eventuali provider cloud:

```bash
hermes profile create domestic
```

Apri il configuratore dei modelli per il profilo:

```bash
hermes -p domestic model
```

Seleziona:

```text
Custom endpoint / self-hosted
```

Inserisci:

```text
API mode:      OpenAI chat completions
Base URL:      http://127.0.0.1:18080/v1
API key:       valore DOMESTICLLM_API_KEY
Model:         deepseek-v4-flash
Context:       100000
```

Hermes supporta endpoint self-hosted che implementano `/v1/chat/completions`, inclusi `llama.cpp`, vLLM, Ollama e server compatibili. DS4 implementa chat completions, streaming e tool calling OpenAI-compatible. ([GitHub][6])

---

# 8. Configurazione manuale raccomandata

Apri la configurazione del profilo:

```bash
hermes -p domestic config edit
```

La parte rilevante dovrebbe essere equivalente a:

```yaml
providers:
  domestic:
    api: http://127.0.0.1:18080/v1
    key_env: DOMESTICLLM_API_KEY
    transport: chat_completions

    models:
      deepseek-v4-flash:
        context_length: 100000

model:
  provider: custom:domestic
  default: deepseek-v4-flash
  context_length: 100000

terminal:
  backend: local
  timeout: 300

approvals:
  mode: manual
  timeout: 120
```

La sintassi corrente di Hermes permette provider custom nominati sotto `providers:` e la selezione tramite `custom:nome-provider`. ([GitHub][2])

Controlla:

```bash
hermes -p domestic dump
hermes -p domestic doctor
```

Devi vedere indicativamente:

```text
provider: custom:domestic
model: deepseek-v4-flash
terminal: local
context: 100000
```

---

# 9. Avvio su una codebase locale

Entra sempre nel repository prima di avviare Hermes:

```bash
cd ~/src/nome-progetto
```

Controlla lo stato Git:

```bash
git status --short
git branch --show-current
```

È prudente creare un branch:

```bash
git switch -c agent/hermes-review
```

Avvia:

```bash
hermes -p domestic
```

Il client CLI usa come directory operativa la directory dalla quale viene avviato. Il backend `local` esegue terminale e operazioni sui file con i permessi dell’utente WSL corrente. ([GitHub][7])

## Primo test in sola lettura

Invia a Hermes:

```text
Analizza questo repository in sola lettura.

Prima esegui soltanto:
1. pwd
2. git status --short
3. git branch --show-current
4. find . -maxdepth 2 -type f | sort | head -200

Non modificare file.
Non installare dipendenze.
Non eseguire comandi con sudo.
Riassumi architettura, dipendenze, punti di ingresso e rischi.
```

Poi controlla:

```bash
git status --short
```

Non deve risultare alcuna modifica.

## Test di modifica controllata

```text
Individua un miglioramento piccolo e reversibile.

Prima mostra:
- file interessato;
- problema;
- patch proposta;
- comando di test.

Non modificare nulla prima della mia approvazione.
```

Mantieni `approvals.mode: manual`. Non usare:

```bash
hermes --yolo
```

Hermes dispone di controlli sui comandi pericolosi, ma la sua stessa documentazione precisa che il vero confine di sicurezza è il sistema operativo, non il filtro interno dell’agente. ([GitHub][8])

---

# 10. Selezione del modello da Hermes

Dentro una sessione puoi vedere il modello corrente con:

```text
/model
```

Per selezionare DS4:

```text
/model custom:domestic:deepseek-v4-flash
```

Per renderlo predefinito:

```text
/model custom:domestic:deepseek-v4-flash --global
```

Hermes permette il cambio di modello durante la sessione, ma può scegliere soltanto provider ed endpoint già configurati. ([GitHub][9])

## Limite importante

Il comando Hermes:

```text
/model qwen
```

**non avvia automaticamente Qwen sul server**.

Hermes cambia il valore `model` della richiesta o l’endpoint selezionato. Non controlla:

* `systemctl`;
* la console DomesticLLM;
* caricamento o scaricamento dei GGUF;
* allocazione GPU;
* arresto di DS4;
* avvio di `llama.cpp`.

Inoltre, nel server DS4 gli alias modello indicano il modello già caricato: non servono a caricare un GGUF differente. ([GitHub][1])

---

# 11. Come gestire più modelli correttamente

## Soluzione attuale, semplice e affidabile

Un solo endpoint espone il catalogo aggregato dei runtime attivi:

```text
porta server 8080 (gateway)
porta WSL 18080 (tunnel)
DS4 capacity lane :8083
llama.cpp fast lane :8085
```

Configurazione Hermes:

```yaml
providers:
  domestic:
    api: http://127.0.0.1:18080/v1
    key_env: DOMESTICLLM_API_KEY
    transport: chat_completions
    models:
      deepseek-v4-flash:
        context_length: 100000

model:
  provider: custom:domestic
  default: deepseek-v4-flash
```

Quando Qwen sarà validato a 64k:

```yaml
  domestic:
    models:
      qwen3-coder:
        context_length: 65536
```

Se il relativo runtime è già attivo, Hermes potrà cambiare endpoint con:

```text
/model custom:domestic:qwen3-coder
```

## Perché non avviare tutti i modelli

Sul vostro hardware sarebbe controproducente:

* maggiore consumo RAM;
* occupazione contemporanea delle GPU;
* competizione sulla KV cache;
* maggiore rischio di OOM;
* peggioramento del tempo di risposta;
* impossibilità di attribuire correttamente i problemi a un runtime.

DomesticLLM è deliberatamente costruito per impedire l’avvio contemporaneo di più processi modello molto pesanti.

---

# 12. Evoluzione professionale: un `modelctl` per DomesticLLM

Per ottenere davvero:

```text
“usa Qwen”
“usa DS4”
“usa Cyber”
```

direttamente da Hermes, DomesticLLM necessita di un piccolo **control plane**, non di un altro agente.

Il componente dovrebbe:

1. accettare esclusivamente alias predefiniti;
2. usare un lock globale;
3. impedire due runtime contemporanei;
4. arrestare il runtime corrente;
5. avviare l’unità systemd corretta;
6. attendere `/v1/models`;
7. eseguire uno smoke test;
8. pubblicare il backend solo dopo esito positivo;
9. ripristinare il modello precedente in caso di errore;
10. registrare operatore, modello, orario e risultato;
11. limitare la frequenza dei cambi;
12. non accettare nomi di servizio arbitrari provenienti dal modello.

Esempio concettuale:

```text
modelctl use ds4
modelctl use qwen
modelctl status
modelctl list
```

Mappatura interna fissa:

```text
ds4   → profilo DeepSeek V4 Flash → DS4 server
qwen  → profilo Qwen Coder        → llama.cpp
cyber → profilo BugTraceAI        → llama.cpp
```

Non deve esistere qualcosa come:

```text
modelctl use "$(testo_generato_dal_modello)"
```

Il modello deve poter scegliere solo da una whitelist.

La versione iniziale non dovrebbe essere richiamabile autonomamente da Hermes. Il cambio modello deve rimanere un’azione dell’operatore, almeno finché ogni profilo non supera i test agentici.

---

# 13. Impostazioni consigliate per hardware non molto performante

## Hermes

* un solo agente principale;
* niente subagenti paralleli durante i primi test;
* niente analisi simultanea di più repository;
* compressione della sessione quando cresce;
* richieste precise e suddivise;
* evitare di inviare file binari, `node_modules`, `.venv`, build e cache;
* creare `AGENTS.md` concisi per ogni progetto.

## DS4

* contesto: `100000`, come profilo validato;
* KV disk cache attiva;
* un solo processo modello pesante;
* backend stabile su `8082`;
* canary separato su `8083`;
* potenza ridotta solo dopo benchmark;
* mantenere il server attivo tra richieste per riutilizzare prefissi e KV.

DS4 è progettato per riutilizzare il prefisso delle conversazioni e può conservare checkpoint KV su disco, riducendo il costo dei turni successivi e dei riavvii. ([GitHub][10])

---

# 14. Telegram: un solo percorso operativo

Hermes include già un gateway Telegram con streaming, allegati, sessioni e
allowlist. È il percorso operativo di DomesticLLM: evita un secondo bridge che
duplicherebbe memoria, gestione sessioni e tool calling.

`antirez/botlib` resta un riferimento architetturale C/BSD-3-Clause per bot
longevi e minimali. Non viene messo in parallelo al gateway Hermes; potrà essere
usato in futuro per un bot di sola osservabilità, senza terminale né strumenti.

Configurazione minima in `~/.hermes/.env` (permessi `0600`):

```dotenv
DOMESTICLLM_API_KEY=CHIAVE_GATEWAY
TELEGRAM_BOT_TOKEN=TOKEN_DA_BOTFATHER
TELEGRAM_ALLOWED_USERS=ID_TELEGRAM_NUMERICO
HERMES_STREAM_READ_TIMEOUT=1800
```

Non impostare `GATEWAY_ALLOW_ALL_USERS=true`. Hermes nega gli utenti per
default quando manca una allowlist; DomesticLLM rende l'allowlist obbligatoria.

Il setup interattivo e l'avvio sono azioni di rete/servizio soggette a gate
umano:

```bash
hermes gateway setup
hermes gateway start
hermes gateway status
```

Per un gruppo, mantieni `telegram.require_mention: true` e aggiungi soltanto gli
ID chat approvati. Il processo Hermes gira in WSL, quindi file e terminale
restano sul laptop; Telegram non parla mai direttamente con DS4.

# 15. Controlli finali

## Server

```bash
sudo ss -ltnp | grep -E ':(8080|8082|8083|8084|8085)\b'
printf 'header = "Authorization: Bearer %s"\n' "$DOMESTICLLM_API_KEY" | \
  curl --config - -fsS http://127.0.0.1:8080/v1/models | jq
```

La porta deve apparire come:

```text
127.0.0.1:8083
```

Non:

```text
0.0.0.0:8083
```

## WSL

```bash
ssh -G domesticllm | grep -E \
  'hostname|user|identityfile|localforward'
```

Con tunnel aperto:

```bash
printf 'header = "Authorization: Bearer %s"\n' "$DOMESTICLLM_API_KEY" | \
  curl --config - -fsS http://127.0.0.1:18080/v1/models | jq
```

## Hermes

```bash
hermes -p domestic doctor
hermes -p domestic dump
```

## Repository

```bash
cd ~/src/nome-progetto
git status --short
hermes -p domestic
```

---

# Architettura finale raccomandata

```text
WSL2
└── Hermes Agent
    ├── terminal backend locale
    ├── repository locali
    ├── approvazioni manuali
    └── provider custom:domestic
           │
           ▼
    127.0.0.1:18080
           │
           ▼
    SSH tunnel su Tailscale
           │
           ▼
Server DomesticLLM
└── 127.0.0.1:8080 (gateway autenticato)
    ├── DS4 / DeepSeek V4 Flash
        ├── tool calling
        ├── streaming
        ├── contesto 100k
    │   └── KV cache su NVMe
    └── llama.cpp fast lane (chat, profilo attivo)
```

**Conclusione:** non installare DwarfStar come agente dentro WSL. Mantieni **Hermes in WSL per lavorare sui file locali** e **DS4 sul server come backend remoto**. Per ora usa DeepSeek V4 Flash come unico modello agentico; Qwen, Dolphin e Cyber richiedono una fase separata di validazione prima di poter ricevere strumenti o accesso alle codebase.

[1]: https://github.com/antirez/ds4?ref=ssp.sh&utm_source=chatgpt.com "GitHub - antirez/ds4 at ssp.sh · GitHub"
[2]: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/providers.md "hermes-agent/website/docs/integrations/providers.md at main · NousResearch/hermes-agent · GitHub"
[3]: https://tailscale.com/docs/install/windows/wsl2?utm_source=chatgpt.com "Install Tailscale on Windows with WSL 2 · Tailscale Docs"
[4]: https://learn.microsoft.com/en-us/windows/wsl/networking?utm_source=chatgpt.com "Accessing network applications with WSL | Microsoft Learn"
[5]: https://github.com/NousResearch/hermes-agent "GitHub - NousResearch/hermes-agent: The agent that grows with you · GitHub"
[6]: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/providers.md?utm_source=chatgpt.com "hermes-agent/website/docs/integrations/providers.md at main · NousResearch/hermes-agent · GitHub"
[7]: https://github.com/nousresearch/hermes-agent/blob/main/website/docs/reference/environment-variables.md?utm_source=chatgpt.com "hermes-agent/website/docs/reference/environment-variables.md at main · NousResearch/hermes-agent · GitHub"
[8]: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/security.md?utm_source=chatgpt.com "hermes-agent/website/docs/user-guide/security.md at main · NousResearch/hermes-agent · GitHub"
[9]: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/slash-commands.md?utm_source=chatgpt.com "hermes-agent/website/docs/reference/slash-commands.md at main · NousResearch/hermes-agent · GitHub"
[10]: https://github.com/antirez/ds4/blob/main/README.md?utm_source=chatgpt.com "ds4/README.md at main · antirez/ds4 · GitHub"
