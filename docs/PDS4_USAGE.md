# Uso operativo PDS4

PDS4 espone il gateway LAN senza credenziali su `http://SERVER:8080`. La
release operativa carica esclusivamente tre modelli sulla Fast lane, uno alla
volta, senza usare DeepSeek Flash:

```text
qwen3-coder-q4
dolphin-mistral-24b-q4
dolphin-cyber-8b-q4
```

La pagina web è disponibile direttamente all'indirizzo del server. Per una
chat da terminale:

```bash
export PDS4_URL=http://127.0.0.1:8080/v1/chat/completions
/opt/pds4/current/bin/pds4 tui --model dolphin-cyber-8b-q4
```

Per cambiare modello:

```bash
sudo /opt/pds4/current/bin/pds4 lane use fast qwen3-coder-q4
sudo /opt/pds4/current/bin/pds4 lane use fast dolphin-mistral-24b-q4
sudo /opt/pds4/current/bin/pds4 lane use fast dolphin-cyber-8b-q4
```

Durante il cambio il gateway restituisce `warming`; se la canary fallisce il
modello precedente viene ripristinato.

API OpenAI-compatible:

```bash
curl http://SERVER:8080/v1/models | jq
curl http://SERVER:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"dolphin-cyber-8b-q4","messages":[{"role":"user","content":"Ciao"}],"max_tokens":128}'
```

Stato e log:

```bash
sudo /opt/pds4/current/bin/pds4 lane status
sudo /opt/pds4/current/bin/pds4 doctor
sudo systemctl status pds4-fast@dolphin-cyber-8b-q4.service
sudo journalctl -u pds4-fast@dolphin-cyber-8b-q4.service -f
```

Il gateway è aperto alla LAN configurata: limitarlo con firewall o rete
privata, non pubblicarlo su Internet.

## Benchmark e raccolta dati

La suite integrata esegue prompt deterministici di matematica, biologia e
coding e salva un JSONL con latenza, time-to-first-token, token/s, risultato
HTTP e risposta. Eseguirla sul server:

```bash
sudo /opt/pds4/current/bin/pds4-benchmark-suite \
  --url http://127.0.0.1:8080/v1/chat/completions \
  --models qwen3-coder-q4,dolphin-mistral-24b-q4,dolphin-cyber-8b-q4 \
  --switch --output /srv/pds4/benchmarks/run-$(date +%Y%m%d-%H%M%S).jsonl
```

Ripetere dopo modifiche a runtime, contesto, batch, cache KV o affinità CPU.
I JSONL restano locali e non vengono inviati a servizi esterni.
