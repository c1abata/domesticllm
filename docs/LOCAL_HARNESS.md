# DomesticLLM local harness

The harness runs on the operator laptop. Inference remains on one or more
DomesticLLM servers. It uses the OpenAI-compatible endpoints already exposed by
the server, stores conversation history locally in SQLite, and routes requests
with small deterministic rules.

It does **not** implement MLA, MoE routing, KV compression, prompt compression,
or speculative decoding in Python. Those are model/runtime responsibilities.
DeepSeek DSpark speculation, when supported, must be configured in the DS4
runtime. The harness only sends requests, selects an explicitly configured
profile, records timings, and preserves local conversation state.

## Recommended topology

```text
Ubuntu laptop
  domestic-harness
  ~/.config/domesticllm/harness.toml
  ~/.local/state/domesticllm-harness/harness.sqlite3
          |
          | Tailscale or trusted wired LAN; bearer key
          v
Ubuntu inference server
  :8080 Qwen3 Coder via llama-server
  :8082 DeepSeek V4 Flash via DS4 or llama-server
  :8083 optional specialist model
```

A single model server can expose only the model currently loaded by that
service. Configure multiple profiles only when the corresponding endpoints
really exist. The router never starts models and never silently substitutes one
profile for another.

## Laptop installation

```bash
git clone https://github.com/c1abata/domesticllm.git
cd domesticllm/harness
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .

mkdir -p ~/.config/domesticllm
install -m 600 harness.example.toml ~/.config/domesticllm/harness.toml
```

Edit `~/.config/domesticllm/harness.toml`. Remove profiles whose services are
not installed. Prefer Tailscale addresses or a dedicated trusted VLAN. Plain
HTTP must not cross an untrusted network.

Load the API keys without putting them in TOML:

```bash
install -d -m 700 ~/.config/environment.d
cat > ~/.config/environment.d/domesticllm.conf <<'EOF'
DOMESTICLLM_QWEN_KEY=replace-with-qwen-key
DOMESTICLLM_DEEPSEEK_KEY=replace-with-deepseek-key
DOMESTICLLM_SECURITY_KEY=replace-with-security-key
EOF
chmod 600 ~/.config/environment.d/domesticllm.conf
systemctl --user daemon-reload
```

For the current shell, export the same variables manually or log out and in.
Do not copy `/etc/local-ai-*.key` through chat, shell history, or Git.

## Server checks

On the server, confirm each service separately:

```bash
sudo systemctl status local-ai-ds4-nvidia --no-pager
sudo ss -lntp
sudo ufw status verbose
```

The existing NVIDIA installer binds to loopback by default. To serve a laptop,
use either an SSH tunnel or deliberately bind the gateway to the Tailscale/LAN
address and allow only the laptop CIDR. Keep the bearer key enabled.

Safer SSH-tunnel example from the laptop:

```bash
ssh -N \
  -L 18080:127.0.0.1:8080 \
  -L 18082:127.0.0.1:8082 \
  operator@SERVER_TAILSCALE_IP
```

Then use `http://127.0.0.1:18080` and `http://127.0.0.1:18082` in TOML. This
keeps inference services on server loopback.

## First run

```bash
domestic-harness check

domestic-harness ask --profile qwen --meta \
  "Scrivi un piccolo parser TOML in Python"

domestic-harness ask --profile deepseek --session architecture --meta \
  "Analizza i rischi di questa architettura"

domestic-harness clear --session architecture
```

`check` verifies `/health` and `/v1/models`. A profile that fails is reported as
an error; there is no hidden fallback.

## Routing

The router is intentionally transparent:

- security terms select the first profile declaring `security`;
- coding terms select the first profile declaring `code`;
- architecture/reasoning terms select the first profile declaring `reasoning`;
- other prompts use a `general` profile or the configured default.

Use `--profile NAME` whenever model choice matters. Configuration order defines
priority among profiles with the same capability.

## Performance rules

1. Keep the model resident. Repeated model swapping costs more than router logic.
2. Use Qwen3 Coder for fast coding on the validated DomesticLLM workstation.
3. Use DeepSeek V4 Flash when its quality justifies its lower throughput.
4. Keep history bounded. The default is 24 messages; large histories increase
   prefill cost and KV use.
5. Measure with `--meta`. Compare elapsed time and server token counters before
   changing context, batch, cache, or GPU placement.
6. Do not install vector databases until a real corpus requires retrieval.
   SQLite conversation state is sufficient for the first production path.
7. Do not compress prompts automatically. Destructive compression can remove
   exact code, paths, constraints, and tool outputs.

## Tool execution boundary

This first release does not execute shell commands. Model output is untrusted.
Add tools later as separate allowlisted executables, each with fixed arguments,
timeouts, output limits, an unprivileged account, and an explicit human approval
step for writes or network changes.
