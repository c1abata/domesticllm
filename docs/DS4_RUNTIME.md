# Runtime DS4 CUDA nativo

Questo percorso promuove DS4 da riferimento diagnostico a canary servibile,
senza rimuovere il backend `llama.cpp`. Il target è Ubuntu 24.04, Ryzen 9
5950X, 128 GiB, NVMe e due RTX A4500 (`sm_86`).

## Confini di sicurezza

- Il build è non-root, offline e accetta solo il commit bloccato in
  `conf/ds4-runtime.lock`.
- Driver NVIDIA e CUDA Toolkit sono prerequisiti: nessuno script li installa.
- Nessuno script scarica modelli. Il GGUF `q2-imatrix` deve essere fornito
  dall'operatore e deve superare SHA-256 prima di ogni avvio.
- DS4 ascolta solo su `127.0.0.1`. L'accesso remoto passa da tunnel SSH o
  tailnet approvato; non esiste autenticazione nativa da usare come barriera LAN.
- Modelli e release sono root-owned e non scrivibili da `localai`.
- I dati scrivibili del servizio sono limitati alla KV cache da 8 GiB e ai log.

Dal laptop, il bind resta loopback anche usando Tailscale:

```bash
ssh -N -L 8083:127.0.0.1:8083 operatore@server-tailnet
```

Il client usa quindi `http://127.0.0.1:8083`; non si apre la porta DS4 in LAN.

## Build e installazione

Preparare separatamente un checkout DS4 già fermo al commit richiesto. La rete
e il download restano un gate umano e non fanno parte di questi script.

```bash
scripts/14_build_ds4_native.sh \
  --source /srv/build/ds4-80df56af4070d0fc62f6f9682b1854f8e5be8b00

sudo install -o root -g localai -m 0440 \
  /percorso/verificato/Huihui-DeepSeek-V4-Flash-BF16-abliterated-ds4-Q2.gguf \
  /opt/local-ai/models/

sudo scripts/15_install_ds4_native.sh \
  --artifact artifacts/ds4-80df56af4070d0fc62f6f9682b1854f8e5be8b00 \
  --start-canary
```

Il build compila i target di test upstream ed esegue estrattori, agent, parser
server, placement, argomenti GPU e sampling senza caricare il modello. I test
del modello sono successivi e usano esplicitamente SSD streaming sul target;
il percorso residente implicito di `make test` non è adatto a 20 GiB di VRAM.

Le release sono in `/opt/local-ai/releases/<sha>`. `/opt/local-ai/current` e
`/opt/local-ai/previous` sono symlink sostituiti atomicamente. Il canary usa
`127.0.0.1:8083`, contesto
100k e KV disk in `/var/cache/local-ai/ds4/kv` con budget 8192 MiB.

## Health e benchmark

DS4 al commit bloccato espone `/v1/models`, non un contratto `/health`. Perciò:

```bash
sudo scripts/16_ds4_health.sh preflight
scripts/16_ds4_health.sh health

scripts/17_benchmark_ds4_acceptance.sh \
  --backend ds4 \
  --prompt-file benchmarks/acceptance.txt \
  --output-dir benchmarks/results/ds4-run-01
```

Eseguire un backend enorme alla volta. Per `llama`, fermare DS4, avviare la
baseline e ripetere lo stesso comando con `--backend llama` e, se necessario,
`--api-key-file /percorso/root-only/api-key`. L'evidenza include stream SSE
grezzo, TTFT del primo delta, prefill/decode token/s quando il backend restituisce
`usage`, durata totale, RSS e campioni GPU ogni 500 ms. Per DS4 il comando
termina non-zero se GPU0 non lavora o se la GPU1 riservata viene usata. I
log del profiler restano necessari per i dati di cache hit affidabili.

Il test di quattro ore resta un gate hardware. Il profilo domesticLLM usa il
percorso CUDA SSD streaming esplicito del runtime bloccato: GPU0, cache esperti
da 6 GB, `--power 100`. Il budget conserva margine per prefill oltre 2k token;
8 GB ha prodotto OOM sul target. Non usa unified memory né spill implicito. GPU1 resta
isolata per una fast lane separata, da riattivare solo dopo l'accettazione DS4.

`DS4_BATCHED_SESSIONS=1` è intenzionale con contesto 100k: ogni sessione
aggiuntiva possiede un KV residente. La prova a 2 sessioni è un canary separato
con gate di correttezza, VRAM/RSS, fairness, soak e rollback; vedere
`docs/DS4_MXFP4.md`.

## Promozione e rollback

La promozione richiede un file root-owned, non scrivibile da gruppo/altri:

```text
CORRECTNESS=pass
TOOL_CALLING=pass
DECODE_NOT_BELOW_BASELINE=pass
TTFT_WITHIN_10_PERCENT=pass
GPU_ISOLATION=pass
STRESS_4H=pass
ROLLBACK_TESTED=pass
```

```bash
sudo scripts/18_promote_ds4_native.sh \
  --acceptance-file /root/ds4-acceptance.env \
  --confirm PROMOTE_DS4
```

Lo script verifica il canary, ferma DS4, ferma la baseline sulla 8082, sposta
DS4 sulla 8082 e richiede health positivo. Un fallimento termina non-zero e
non tenta altre mutazioni. Il rollback è quindi una decisione esplicita:

```bash
sudo scripts/19_rollback_llama.sh --confirm ROLLBACK_LLAMA
```

Il rollback ferma DS4, ripristina la sua configurazione canary e riattiva
`llama.cpp` sulla 8082. L'unità `local-ai-llama-fallback.service` resta
disabilitata e può essere avviata manualmente sulla 8084 durante la fase DS4.

Il profilo nativo usa `--power 70` per limitare calore e rumore domestici senza
alterare l'output. MTP/DSpark, P2P e altri percorsi sperimentali restano spenti:
qualsiasi ottimizzazione successiva deve partire da un gap riproducibile.
