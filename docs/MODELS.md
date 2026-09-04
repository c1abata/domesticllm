# Modelli del gateway principale

Il catalogo è definito in `config/lan-models.json`. I pesi restano fuori da Git
e ogni attivazione verifica lo SHA-256 registrato.

| ID API/UI | Stato | Uso | Configurazione GPU |
| --- | --- | --- | --- |
| `dolphin-8b-q4` | ammesso | chat locale uncensored | GPU 0 |
| `qwen3-coder-30b-ud-q4` | ammesso | coding e assistenza generale | entrambe le RTX A4500 |
| `deepseek-v4-flash-iq2` | non ammesso | riferimento DS4 | nessuna, restituisce `409` |

Il gateway esegue un solo backend alla volta. Se si cambia modello, termina il
processo precedente, attende il rilascio delle risorse, verifica il file e
avvia il profilo successivo.

## Limite DeepSeek

Il GGUF DeepSeek V4 Flash IQ2 non entra nel budget effettivo delle due RTX
A4500 da 19 GiB. Il test nativo DS4 con tensor parallelism e SSD streaming ha
fallito il placement della stage bilanciata; per questo il profilo resta nel
catalogo ma è disabilitato. Non rimuovere questo gate senza una nuova prova
hardware riproducibile.

## Regole di modifica

Un nuovo modello richiede: file già presente localmente, SHA-256 nel catalogo,
profilo esplicito, smoke test, benchmark e verifica di rilascio memoria dopo
almeno tre esecuzioni consecutive. Non scaricare pesi durante avvio o richiesta.
