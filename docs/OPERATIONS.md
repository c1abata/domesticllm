# Operazioni del servizio principale

Il servizio remoto è `cpu-inference-lan-gateway.service` e gira come user
service di `ale` sul server `10.25.13.22`.

## Stato e log

```bash
systemctl --user status cpu-inference-lan-gateway.service
journalctl --user -u cpu-inference-lan-gateway.service -f
curl -fsS http://127.0.0.1:8080/ui/status
```

Lo stato mostra modello, runtime, durata della sessione, numero di richieste e
le metriche dell’ultima risposta non streaming.

## Riavvio

```bash
systemctl --user restart cpu-inference-lan-gateway.service
systemctl --user is-active cpu-inference-lan-gateway.service
```

Un riavvio termina il backend caricato. La richiesta successiva ricarica il
modello selezionato e aggiorna lo stato della sessione.

## Controlli minimi

```bash
curl -fsS http://127.0.0.1:8080/
curl -o /dev/null -s -w '%{http_code}\n' http://127.0.0.1:8080/v1/models
nvidia-smi --query-gpu=name,memory.used --format=csv,noheader
```

Il secondo comando deve restituire `401` senza token. Per le API, ottenere il
token solo dal server con `scripts/show-api-token.sh`; non salvarlo in URL,
repository, log o screenshot.

## Ripristino

Se il servizio non parte, controllare prima sintassi del catalogo, presenza e
SHA-256 dei GGUF e log del modello in
`~/.local/state/cpu-inference/<model>.log`. Non avviare direttamente backend
su porte LAN: il gateway deve restare l’unico listener esposto.
