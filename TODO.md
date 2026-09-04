# Backlog controllato

La release principale è la console LAN descritta nel README. Nessun elemento di
questo backlog modifica la configurazione stabile senza un ramo sperimentale,
benchmark sul target e rollback verificato.

1. Valutare una build llama.cpp più recente su un ramo separato.
2. Aggiungere streaming SSE e persistenza locale opzionale alla UI.
3. Aggiungere rate limiting configurabile e log strutturati al gateway.
4. Riesaminare DeepSeek solo con una prova di placement e qualità sulle A4500.
5. Definire profili isolati per audio e video prima di abilitarli.

I sottosistemi PDS4, MCP e Hermes presenti nel repository sono componenti
separati o materiale di recovery: non sono il percorso operativo principale.
