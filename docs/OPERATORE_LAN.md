# Procedura operatore LAN/Tailscale

Questa è la procedura breve per rendere DomesticLLM operativo su
`10.25.13.22`. L'operatore deve eseguire i comandi sul server; non deve
modificare i nomi dei modelli.

## 1. Aggiornare il checkout

```bash
cd /home/ale/localdev
git clone https://github.com/c1abata/domesticllm.git domesticllm  # solo la prima volta
cd domesticllm
git pull --ff-only origin main
```

## 2. Verificare i quattro GGUF già caricati

I nomi pubblici obbligatori sono:

```text
deepseek-v4-flash   DeepSeek V4 Flash (DS4, GPU0)
dolphin             Dolphin 3.0 Mistral 24B (GPU1, profilo selezionabile)
qwen                Qwen3 Coder 30B (GPU1, profilo selezionabile)
cyber-uncensored    Dolphin Cyber 8B abliterated (GPU1, profilo selezionabile)
```

I file devono trovarsi in `/opt/local-ai/models/` con i nomi definiti nei
file `conf/`. Non rinominare i file e non creare un alias `gpt-oss`.

## 3. Installare runtime e servizi

```bash
sudo bash scripts/05_prepare_ubuntu_server.sh --models-dir /opt/local-ai/models
sudo bash scripts/14_build_ds4_native.sh \
  --source /srv/build/ds4-80df56af4070d0fc62f6f9682b1854f8e5be8b00
sudo bash scripts/15_install_ds4_native.sh \
  --artifact artifacts/ds4-80df56af4070d0fc62f6f9682b1854f8e5be8b00 \
  --start-canary
sudo bash scripts/25_install_unified_ds4.sh
```

Installare la fast lane e il gateway:

```bash
sudo install -d -o root -g localai -m 0750 /opt/local-ai/models
sudo bash scripts/23_install_cyber_model.sh
sudo bash scripts/21_install_lan_gateway.sh --lan-cidr 0.0.0.0/0
```

Il servizio DS4, la fast lane e il gateway ascoltano su `0.0.0.0`. Il gateway
Web/API è su `http://10.25.13.22:8080/`; usare l'indirizzo Tailscale
equivalente quando si è sulla tailnet.

## 4. Avviare un profilo veloce

La GPU1 esegue un solo profilo alla volta:

```bash
sudo domesticllm-model dolphin
# oppure: sudo domesticllm-model qwen
# oppure: sudo domesticllm-model cyber-uncensored
```

Per tornare a DeepSeek e liberare GPU1:

```bash
sudo domesticllm-model stop
sudo systemctl restart local-ai-ds4-native.service
```

## 5. Usare Web UI e CLI

Aprire `http://10.25.13.22:8080/`, inserire la chiave mostrata da:

```bash
sudo cat /etc/local-ai-gateway.key
```

La CLI punta allo stesso gateway e accetta soltanto i quattro nomi pubblici:

```bash
export DOMESTICLLM_URL=http://10.25.13.22:8080/v1/chat/completions
export LOCAL_AI_API_KEY_FILE=$HOME/.config/domesticllm/lan.key
domesticllm-tui --model deepseek-v4-flash
domesticllm-lan --model dolphin "test rapido"
```

Per Hermes/WSL, impostare nel suo `.env` l'URL `http://10.25.13.22:8080/v1`
e la stessa chiave; non inserire la chiave nella riga di comando o in un URL.

## 6. Controllo rapido

```bash
curl -fsS http://10.25.13.22:8080/
curl -fsS -H "Authorization: Bearer $(sudo cat /etc/local-ai-gateway.key)" \
  http://10.25.13.22:8080/v1/models | jq
systemctl --no-pager --full status local-ai-ds4-native.service domesticllm-llama-fast.service domesticllm-lan-gateway.service
```

Se un modello veloce non compare, attivarlo con `sudo domesticllm-model NOME` e
attendere che `systemctl status domesticllm-llama-fast` sia `active (running)`.
