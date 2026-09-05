# DomesticLLM — console LAN principale

Questa è la versione stabile principale del progetto. Offre un solo gateway di
inferenza locale sulla LAN: la console web per le persone e le API compatibili
OpenAI per i client.

## Uso

- Console web: `http://10.25.13.22:8080/` — nessun login.
- API: `http://10.25.13.22:8080/v1/*` — Bearer token obbligatorio.
- Stato pubblico della console: `http://10.25.13.22:8080/ui/status`.
- Stato API autenticato: `GET /v1/host/status`.

Il token API è locale alla macchina e non viene mostrato dalla pagina web:

```bash
ssh ale@10.25.13.22 /home/ale/cpu-inference/scripts/show-api-token.sh
```

## Modelli disponibili

Il gateway carica un solo backend alla volta, liberando memoria prima di ogni
cambio modello.

- `dolphin-8b-q4`: modello uncensored rapido su GPU 0.
- `qwen3-coder-30b-ud-q4`: modello coding principale, distribuito sulle due
  RTX A4500.
- `kalidroid-27b-q4-vision`: Qwen 3.5 uncensored con projector vision, su GPU 0
  con contesto iniziale da 4K.

DeepSeek V4 Flash IQ2 resta archiviato ma non è un profilo del gateway: DS4 non
riesce a collocarlo in sicurezza nelle due A4500 da 19 GiB.

La console responsiva usa Alpine.js vendorizzato e funziona offline. Permette di
scegliere modello, prompt di sistema, parametri di generazione, seed, stop
sequence, contesto, slot, Flash Attention e cache KV; ogni campo include una
spiegazione pratica. Conversazioni, bozze e impostazioni sono organizzate per
chat e persistono soltanto nel `localStorage` del browser, con esportazione JSON
e cancellazione esplicita.

## Stato e prestazioni

La pagina mostra modello attivo, durata e numero di richieste della sessione.
Dopo ogni risposta non streaming riporta token di prefill/output e le velocità
misurate di prefill e generazione in token/s.

## Servizio remoto

Sul server il servizio principale è:

```bash
systemctl --user status cpu-inference-lan-gateway.service
```

Il gateway è l’unico processo esposto, in ascolto su `0.0.0.0:8080`. I processi
dei modelli restano su `127.0.0.1`. La guida operativa completa è in
[docs/LAN_GATEWAY.md](docs/LAN_GATEWAY.md).

I servizi video secondari sono mantenuti separati e disabilitati: non condividono
la sessione GPU della console principale.

## Verifica rapida

```bash
curl -fsS http://10.25.13.22:8080/ui/status
curl -o /dev/null -s -w '%{http_code}\n' http://10.25.13.22:8080/v1/models
```

Il secondo comando restituisce `401` senza token: è il comportamento atteso.

## Documentazione

- [Architettura](docs/ARCHITECTURE.md): componenti, rete, ciclo di una richiesta
  e confini del servizio.
- [Gateway LAN](docs/LAN_GATEWAY.md): contratto HTTP, autenticazione e stato.
- [Modelli](docs/MODELS.md): catalogo effettivo e limite DeepSeek.
- [Operazioni](docs/OPERATIONS.md): controllo, log, riavvio e diagnosi.
- [Audio opzionale](docs/QWEN_ASR.md): componente separato, non incluso nel
  servizio principale.
