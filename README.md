# DomesticLLM

[![CI](https://github.com/c1abata/domesticllm/actions/workflows/ci.yml/badge.svg)](https://github.com/c1abata/domesticllm/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

DomesticLLM is a reproducible, operator-controlled local inference stack for
running DeepSeek V4 Flash on workstation-class hardware. It combines the native
[DwarfStar4](https://github.com/antirez/ds4) CUDA runtime with an independently
deployable `llama.cpp` fallback, an authenticated LAN gateway, and a streaming
terminal UI that makes long prefill and thinking phases visible.

The project favors plain C, Python/Bash from the standard system toolchain,
systemd hardening, pinned revisions, explicit checksums, and reversible releases.
Model weights are never stored in this repository.

## Architecture

```text
LAN client
  domesticllm-lan / domesticllm-tui
          │ Bearer authentication
          ▼
  0.0.0.0:8080  DomesticLLM gateway
          │ fixed loopback backend
          ▼
  127.0.0.1:8083  native DS4 CUDA
          │
          ├── verified GGUF on RAM/NVMe
          ├── SSD expert streaming + disk KV cache
          └── dedicated NVIDIA GPU

  127.0.0.1:8084  llama.cpp rollback path (inactive by default)
```

The gateway requires a high-entropy token and is constrained by systemd to an
operator-supplied LAN CIDR. DS4 itself remains on loopback. For untrusted
networks, use an SSH tunnel or add TLS; bearer authentication over plain HTTP
does not prevent LAN traffic interception.

## Validated profile

The reference deployment was validated on Ubuntu, 128 GiB RAM, NVMe, and two
NVIDIA RTX A4500 GPUs (`sm_86`):

- DS4 commit `54b36ed9ba42da31b24f2d1a5feb075c2475dbb1`;
- `llama.cpp` commit `876a4321163249c43ca4e986818fab5ab081f282`;
- 100k context, 8 GiB disk KV cache, 4 GiB hot expert cache;
- one GPU assigned to DS4 while the second remains available for a fast lane;
- four-hour soak: 203/203 successful requests, including tool calls and long KV tests;
- verified fallback inference and rollback.

See [vendor.lock.json](vendor.lock.json) for all immutable source/model inputs.
Hardware results are evidence for this profile, not a guarantee for other hosts.

## Terminal UI

The dependency-free TUI streams responses and shows connection, queue,
prefill/thinking, TTFT, context usage, cache tokens, output tokens, decode rate,
last activity, completion, errors, and a conservative stall warning.

```bash
domesticllm-tui "Explain a skip list"
```

For a configured LAN client:

```bash
mkdir -p ~/.config/domesticllm
chmod 700 ~/.config/domesticllm
printf '%s\n' SERVER_LAN_IP > ~/.config/domesticllm/lan.host
chmod 600 ~/.config/domesticllm/lan.host ~/.config/domesticllm/lan.key
domesticllm-lan "Explain a skip list"
```

The API key belongs in `~/.config/domesticllm/lan.key`; never pass it as a
command-line argument. See [docs/CLI_TUI.md](docs/CLI_TUI.md) for environment
variables and non-interactive operation.

## Build and install

Network access, downloads, package installation, sudo, service changes, and
firewall changes are deliberate operator gates. Build only locked commits and
verify model hashes before startup.

```bash
# Build native DS4 from an exact checkout.
bash scripts/14_build_ds4_native.sh \
  --source /path/to/ds4-checkout \
  --output /path/to/artifacts

# Install the reviewed artifact and loopback service.
sudo bash scripts/15_install_ds4_native.sh \
  --artifact /path/to/artifacts \
  --start-canary

# Explicitly enable authenticated LAN access for one CIDR.
sudo bash scripts/21_install_lan_gateway.sh --lan-cidr YOUR_LAN_CIDR
```

The model downloader rejects unexpected size or SHA-256 and quarantines partial
files. The optional abliterated model profile is experimental and must be used
with human review of outputs:

```bash
sudo MODEL_DIR=/opt/local-ai/models \
  bash scripts/32_fetch_ds4_flash_gguf.sh uncensored-q2
```

Detailed operational documentation:

- [Native DS4 runtime](docs/DS4_RUNTIME.md)
- [NVIDIA deployment](docs/DS4_NVIDIA.md)
- [Models and checksums](docs/MODELS.md)
- [Upstream mapping](docs/ANTIREZ_MAP.md)
- [Build order](docs/BUILD_ORDER.md)

## Verification

```bash
SKIP_MCP_RUNTIME=1 bash tests/run.sh
```

For the locked MCP environment, omit `SKIP_MCP_RUNTIME` after installing
`mcp/requirements.lock`. Linux target validation additionally checks systemd,
the actual CUDA devices, model correctness, stability, performance, and rollback.

## Upstream and attribution

DomesticLLM integrates but does not vendor or impersonate its upstream projects.
The primary sources are:

- [antirez/ds4](https://github.com/antirez/ds4) — MIT;
- [antirez/linenoise](https://github.com/antirez/linenoise) — BSD-2-Clause;
- [antirez/sds](https://github.com/antirez/sds) — BSD-2-Clause;
- [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) — MIT.

The build locks use the public maintenance forks
[`c1abata/ds4`](https://github.com/c1abata/ds4),
[`c1abata/linenoise`](https://github.com/c1abata/linenoise), and
[`c1abata/sds`](https://github.com/c1abata/sds), with upstream provenance
retained in `vendor.lock.json`.

The exact revisions are recorded in [vendor.lock.json](vendor.lock.json).
Upstream names and trademarks remain the property of their respective owners.

## Security and responsible operation

Read [SECURITY.md](SECURITY.md) before exposing any endpoint. DomesticLLM does
not make model output safe or trustworthy: tool calls, generated code, and
uncensored/abliterated model output require validation and least privilege.

## License

DomesticLLM's original integration code and documentation are available under
the [MIT License](LICENSE). Upstream projects and model artifacts retain their
own licenses and terms.
