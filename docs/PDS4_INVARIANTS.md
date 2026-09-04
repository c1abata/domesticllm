# Invarianti di recovery PDS4

Questo file è incluso nei bundle di recovery PDS4 dal codice del repository.
Non descrive il servizio LAN principale, ma conserva le regole minime per quei
bundle:

1. build e avvio non scaricano dati;
2. sorgenti, runtime e modelli hanno revisioni o SHA-256 espliciti;
3. i modelli sono dati non fidati e non vengono eseguiti come codice;
4. pesi e segreti restano fuori da Git;
5. i runtime di recovery restano su loopback;
6. ogni promozione richiede test, rollback e prova sul target;
7. licenze e condizioni di redistribuzione restano vincolanti.
