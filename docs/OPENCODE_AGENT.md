# opencode agent profile

## DomesticLLM native DS4 agent

`domesticllm-agent` avvia esclusivamente il coding agent nativo di DwarfStar4.
Il helper root-owned arresta il server DS4 prima di caricare l'agente, esegue
l'agente e tutti i tool come utente chiamante e ripristina il server all'uscita.
Il lock globale impedisce due processi DS4 contemporanei. Qwen, Mistral,
Dolphin e il profilo cyber restano modelli chat e non sono agent backend.
La TUI gira nella sessione tmux `domesticllm-ds4`: una disconnessione SSH non
interrompe il lavoro e il comando successivo riaggancia la stessa sessione.

```bash
cd /percorso/del/progetto
domesticllm-agent
```

La TUI nativa mostra prefill e generazione. `/save`, `/list`, `/switch`,
`/strip`, `/compact`, `/history`, `/new` e `/power` espongono direttamente i
controlli DS4. Le sessioni persistono in `~/.ds4/kvcache`. Per un singolo turno
non interattivo usare `domesticllm-agent run "richiesta"`.
Per una TUI interattiva senza reasoning usare `domesticllm-agent --direct`;
senza il flag DS4 mantiene il thinking nativo.

Il sudoers dedicato autorizza soltanto il helper validato; non concede shell
root. Il modello DS4 e' pubblico e sola-lettura, mentre le chiavi del gateway
restano inaccessibili all'agente.

AirLLM non e' il backend interattivo: il suo caricamento layer-wise riduce il
picco VRAM ma sposta il collo di bottiglia su disco/PCIe. DomesticLLM ne adotta
il principio solo nella capacity lane DS4 (expert streaming), mentre il coding
canary mantiene Qwen interamente residente su GPU1.

Client side only.

Default 3B/7B profile:

```bash
mkdir -p ~/.config/opencode/agents
cp opencode/opencode.local-lan.json ~/.config/opencode/opencode.json
cp agents/*.md ~/.config/opencode/agents/
```

Edit only the endpoint:
```json
"baseURL": "http://IP_SERVER:8080/v1",
"apiKey": "{env:LOCAL_AI_API_KEY}"
```

Export `LOCAL_AI_API_KEY` from a trusted secret source before starting
OpenCode. Do not write the key into JSON or pass it on a process command line.

Recommended operation:
- Use `plan-local` before edits.
- Use `build-local` for small patches.
- The dynamic Obsidian MCP is intentionally absent from the autonomous path.
- Avoid huge repositories in context.
- Exclude binaries and virtualenvs.

DS4 Intel profile:

```bash
mkdir -p ~/.config/opencode/agents
cp opencode/opencode.ds4-intel-lan.json ~/.config/opencode/opencode.json
cp agents/*.md ~/.config/opencode/agents/
```

Edit only the endpoint:

```json
"baseURL": "http://IP_SERVER:8081/v1",
"apiKey": "{env:LOCAL_AI_API_KEY}"
```

Use DS4 for long planning/build loops where latency is acceptable. Keep the same
agent discipline: small diffs, explicit tool confirmation, no binary context.
