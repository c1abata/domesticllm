# DomesticLLM

[![CI](https://github.com/c1abata/domesticllm/actions/workflows/ci.yml/badge.svg)](https://github.com/c1abata/domesticllm/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

DomesticLLM is a reproducible, operator-controlled local inference stack for
running DeepSeek V4 Flash and a small, curated model set on workstation-class
hardware. It combines the native [DwarfStar4](https://github.com/antirez/ds4)
CUDA runtime with a pinned `llama.cpp` fallback behind one persistent local
console: `ds4`.

The project favors plain C, Python/Bash from the standard system toolchain,
systemd hardening, pinned revisions, explicit checksums, and reversible releases.
Model weights are never stored in this repository.

## Architecture

```text
ds4 (persistent tmux console)
  ├── DeepSeek V4 Flash → native DwarfStar4, SSD expert streaming, persistent KV
  └── Qwen / Mistral / Dolphin / Cyber → pinned llama.cpp fallback

Hermes on WSL / Web UI / CLI-TUI
  └── authenticated gateway → DS4 capacity lane or active llama.cpp fast lane
```

The console remains the direct operator path. An optional dependency-free Web
UI and the Hermes client use the authenticated gateway; DS4 itself remains on
loopback. The stack never exposes an unauthenticated model listener. Model
selection routes requests only to already-active allowlisted profiles and does
not grant a browser or agent permission to control systemd.

## Validated profile

The target workstation is an Asus ProArt X570 class system with Ryzen 9 5950X,
128 GiB RAM, NVMe storage, and two NVIDIA RTX A4500 20 GiB GPUs (`sm_86`). The
validated deployment used:

- DS4 commit `54b36ed9ba42da31b24f2d1a5feb075c2475dbb1` (previous production evidence);
- `llama.cpp` commit `876a4321163249c43ca4e986818fab5ab081f282`;
- 100k context, 8 GiB disk KV cache, 6 GiB hot expert cache;
- one GPU assigned to DS4 while the second remains available for a fast lane;
- four-hour soak: 203/203 successful requests, including tool calls and long KV tests;
- verified fallback inference and rollback.

The current DS4 canary is the requested `ds4f-mxfp4` branch at
`80df56af4070d0fc62f6f9682b1854f8e5be8b00`. Repository checks for this change
ran in Ubuntu/WSL on an Intel Core i5-13420H with 14 GiB visible RAM and no CUDA
device. Therefore build, correctness, two-A4500 activity, soak, performance and
rollback on the target workstation remain release gates; the old installed
release must remain available until they pass.

See [vendor.lock.json](vendor.lock.json) for all immutable source/model inputs.
Hardware results are evidence for this profile, not a guarantee for other hosts.

## Components

| Component | Implementation | Role |
| --- | --- | --- |
| Capacity runtime | pinned native DwarfStar4 CUDA | DeepSeek V4 Flash, tool calls, KV persistence |
| Fast lane | pinned `llama.cpp` CUDA | one active Qwen/Mistral/Dolphin/Cyber profile on GPU1 |
| Operator console | Bash + tmux | one persistent `ds4` control path |
| CLI/TUI | Python standard library | streaming chat, TTFT/token/status telemetry |
| Web UI | static HTML/CSS/JS + Python standard-library gateway | authenticated chat and live model selection |
| WSL harness | Hermes Agent + SSH tunnel | local tools/files with remote inference |
| Telegram | Hermes native gateway | allowlisted messaging from the WSL harness |
| Automation | Bash, systemd, MCP allowlist | reproducible install, health, benchmark and agent checks |

`antirez/botlib` is retained as a small-C design reference. Hermes already owns
the Telegram session/tool lifecycle, so running a second bot bridge would create
two competing paths and is intentionally avoided.

## Unified console

```bash
ds4
```

Inside the console, use `/models`, `/model NAME`, `/status` and `/run`.
The first invocation creates a persistent `tmux` session; subsequent invocations
reattach to it. Use `/help` for the complete command set.

Install the unified entry point after the pinned runtimes and verified models
are present:

```bash
sudo bash scripts/25_install_unified_ds4.sh
```

## Web UI and Hermes

Install the authenticated gateway only after reviewing the approved client
CIDR. This is a network/service human gate:

```bash
sudo bash scripts/21_install_lan_gateway.sh --lan-cidr 100.64.1.25/32
```

Open `http://SERVER:8080/` and paste the gateway key. The key is kept in the
browser tab's session storage, never in a URL or persistent local storage. The
model selector contains only models returned by the live capacity and fast-lane
backends.

For the WSL client, first install Hermes through its reviewed upstream process,
then prepare the offline tunnel definition:

```bash
bash scripts/28_configure_hermes_wsl.sh --ssh-target operator@server-tailnet
```

Review [Hermes on WSL](hermes.md) before enabling the user service or Telegram.

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

# Install the single local operator interface; network services stay disabled.
sudo bash scripts/25_install_unified_ds4.sh
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
- [DS4 MXFP4 branch assessment](docs/DS4_MXFP4.md)
- [Current checkpoint and pending hardware gates](docs/CHECKPOINT.md)
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
- [antirez/botlib](https://github.com/antirez/botlib) — BSD-3-Clause;
- [antirez/linenoise](https://github.com/antirez/linenoise) — BSD-2-Clause;
- [antirez/sds](https://github.com/antirez/sds) — BSD-2-Clause;
- [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) — MIT;
- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — MIT.

The DS4 canary is pinned directly to the requested upstream branch commit.
Linenoise and SDS still use the public `c1abata` maintenance forks, with
upstream provenance retained in `vendor.lock.json`.

The exact revisions are recorded in [vendor.lock.json](vendor.lock.json).
Upstream names and trademarks remain the property of their respective owners.

## Credits

DomesticLLM exists thanks to [Salvatore Sanfilippo (antirez)](https://github.com/antirez),
whose DwarfStar4 work, source code and practical approach to local inference
provided both the technical foundation and the engineering spirit of this
project.

Special thanks also go to the friend of the project who generously donated the
workstation used to build, tune and validate DomesticLLM. That contribution
turned the project from an idea into a tested local-inference system.

## Security and responsible operation

Read [SECURITY.md](SECURITY.md) before exposing any endpoint. DomesticLLM does
not make model output safe or trustworthy: tool calls, generated code, and
uncensored/abliterated model output require validation and least privilege.

## License

DomesticLLM's original integration code and documentation are available under
the [MIT License](LICENSE). Upstream projects and model artifacts retain their
own licenses and terms.
