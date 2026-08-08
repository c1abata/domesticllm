Realizza PoorDwarfStar4/PDS4 adottando come architettura predefinita una
dual lane indipendente:

- Flash lane: DS4 CUDA + DeepSeek V4 Flash su una RTX A4500.
- Fast lane: llama.cpp CUDA + un modello Qwen/Mistral su una seconda RTX A4500.
- CPU AMD: I/O, tokenizzazione, cache, gateway e controllo.

Il requisito principale è la sovranità offline dello stack.

Un operatore deve poter recuperare legalmente modello, pesi, quantizzazione,
tokenizer, template, steering, sorgenti e toolchain; verificarli; conservarli
localmente; trasferirli; ricostruire il runtime; importarli; avviarli e usarli
senza Internet o account cloud.

Prima di implementare:

1. inventaria il repository;
2. correggi le contraddizioni di rete e servizio;
3. non cancellare componenti esistenti;
4. separa codice upstream, patch PDS4 e integrazione;
5. definisci manifest schema v1 e bundle schema v1;
6. identifica le GPU tramite UUID;
7. conserva commit, checksum, licenze e provenienza;
8. considera i modelli dati non fidati;
9. vieta script eseguibili durante l’importazione;
10. mantieni ogni runtime su loopback.

Implementa in PR separate:

PR 1: invarianti, schema manifest, model store e quarantena.
PR 2: unità systemd dual lane e isolamento GPU.
PR 3: modelctl transazionale e rollback.
PR 4: bundle offline, firma, import, export e recovery.
PR 5: KV manager con fingerprint e scritture atomiche.
PR 6: gateway, TUI e Web UI.
PR 7: Hermes e Telegram come adattatori opzionali.
PR 8: benchmark, profiler e tuning dual lane.
PR 9: test di reinstallazione completamente offline.

Per ogni PR:

- mostra problema e confine della modifica;
- preserva licenze e attribuzioni;
- usa dipendenze minime;
- aggiungi test negativi;
- non usare riferimenti floating;
- non effettuare download durante build o startup;
- non promuovere un modello senza smoke test;
- non dichiarare prestazioni senza benchmark hardware;
- documenta rollback e recovery;
- esegui git diff --check, shellcheck, test unitari e test applicabili;
- indica chiaramente gli hardware gate ancora pendenti.

La release è accettabile soltanto se, può essere installata
tramite internet, ma può avviare entrambe le lane, chattare con entrambi i
modelli, cambiare il modello fast, ripristinare la KV, riavviarsi e fare
rollback senza contattare servizi esterni.
