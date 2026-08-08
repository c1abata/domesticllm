- [x] Verificare `antirez/ds4@ds4f-mxfp4`: pin canary aggiornato a
  `80df56af4070d0fc62f6f9682b1854f8e5be8b00`, test scalar MXFP4 aggiunto e
  decisione CUDA/q2 documentata in `docs/DS4_MXFP4.md`.
- [x] Specificare il percorso DwarfStar4 per 2xRTX A4500/128 GiB: q2-imatrix,
  `sm_86`, SSD streaming, GPU0 capacity lane, GPU1 fast lane, KV persistente,
  promozione e rollback espliciti.
- [x] Fornire CLI/TUI e Web UI leggera: gateway standard-library autenticato,
  catalogo aggregato dei runtime vivi e routing DS4/fast lane senza controllo
  servizi dal browser.
- [x] Descrivere nel README hardware target, host di verifica e componenti.
- [x] Integrare Hermes su Ubuntu WSL con tunnel SSH, provider custom, esempi
  offline e Telegram nativo allowlisted. `botlib` resta il riferimento C, non
  un secondo bridge concorrente.
- [ ] Gate hardware: compilare il nuovo pin sul Ryzen 9 5950X/2xA4500, eseguire
  correttezza, attività GPU, benchmark comparativo, soak 4h e rollback prima
  della promozione.
- [ ] Gate operatore: installazione/aggiornamento Hermes, abilitazione del tunnel
  utente, configurazione Telegram, installazione gateway e modifiche servizi o
  firewall richiedono approvazione esplicita sulla macchina destinataria.
