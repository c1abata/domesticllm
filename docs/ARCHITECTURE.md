# Architettura della console LAN

```text
Browser senza login ─┐
                      ├─ 0.0.0.0:8080  gateway Python
Client API con token ─┘       │
                              ├─ 127.0.0.1:18080  Dolphin 8B / llama.cpp
                              ├─ 127.0.0.1:18081  Qwen Coder 30B / llama.cpp
                              └─ 127.0.0.1:18082  Kalidroid 27B Vision / llama.cpp
```

## Componenti

- `scripts/lan-gateway.py`: unico listener LAN, autenticazione API, switching
  seriale, verifica SHA-256 e telemetria di sessione.
- `config/lan-models.json`: catalogo massimo di tre profili e relativi argomenti
  runtime; nessun parametro ROCm/CUDA arbitrario arriva dalla UI.
- `web-lan/index.html`: chat locale senza login e controlli consentiti.
- `deploy/cpu-inference-lan-gateway.service`: unità user systemd.

## Ciclo di una richiesta

1. La UI usa `/ui/chat` senza token; un client API usa `/v1/*` con Bearer token.
2. Il gateway acquisisce il lock della transazione. Se già occupato restituisce
   `429 model_busy`.
3. Verifica il profilo, arresta l’eventuale backend precedente e attende
   `/v1/models` sul loopback.
4. Inoltra la richiesta al backend attivo. Per risposte non streaming registra
   token prompt/output e prefill/generazione token/s.
5. UI e API di stato espongono il risultato; il backend resta caricato fino a
   un cambio modello, riavvio o spegnimento del servizio.

## Confini

Solo il gateway ascolta sulla LAN. I backend restano su loopback e non sono
endpoint pubblici. La UI è intenzionalmente senza login per l’uso su LAN fidata;
le API restano sempre protette dal token locale. Video e audio sono componenti
separati e non condividono processi, cache o sessione GPU con questa console.
