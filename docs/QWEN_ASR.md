# Audio opzionale

Qwen-ASR è un componente separato per trascrizione locale. Non fa parte del
gateway principale, non condivide la sessione GPU e non deve essere avviato
insieme a una generazione LLM sullo stesso hardware senza una verifica di
memoria.

L’installazione, se richiesta, è esplicita:

```bash
sudo bash scripts/22_install_qwen_asr.sh
```

Il servizio principale resta `cpu-inference-lan-gateway.service`. Audio e video
restano disabilitati finché non viene definito un profilo di risorse separato.
