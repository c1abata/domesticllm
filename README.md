# PoorDwarfStar4 (PDS4)

PDS4 is an operator-controlled, offline-recoverable inference stack for one
DeepSeek V4 Flash capacity lane and one replaceable Qwen/Mistral fast lane.
Both runtimes are local, pinned and independently assigned to RTX A4500 GPUs by
UUID. The CPU owns storage I/O, tokenization, gateway, cache and control work.

```text
CLI / TUI / Web / Agent -> authenticated PDS4 gateway
                              |-> Flash: DS4 CUDA, GPU UUID A, 127.0.0.1:8082
                              `-> Fast: llama.cpp, GPU UUID B, 127.0.0.1:8085
```

No build or service startup downloads data. Model weights are untrusted normal
files in a SHA-256 content-addressed store and never enter Git. Runtime services
bind to loopback and deny egress. Telegram is an optional Hermes adapter outside
the inference server.

## Core commands

Per l'uso quotidiano consultare [docs/PDS4_USAGE.md](docs/PDS4_USAGE.md).

```bash
pds4 model inspect models.d/qwen3-coder-q4.json
sudo pds4 model import MANIFEST ARTIFACT_DIRECTORY
sudo pds4 gpu probe --flash GPU-UUID-A --fast GPU-UUID-B
sudo pds4 lane start flash
sudo pds4 lane use fast qwen3-coder-q4
pds4 lane status
pds4 cache list
pds4 doctor
pds4 tui
pds4 serve
```

Fast switching is explicit and transactional. The gateway reports `warming`
during load, never changes services itself, and restores the previous Fast model
when the candidate fails its canary or primary smoke test. Flash is not stopped.

## Offline lifecycle

Reviewed online acquisition is separate from startup:

```bash
pds4 model fetch qwen3-coder-q4
sudo pds4 model import MANIFEST STAGING_DIRECTORY
```

Create and verify locally signed bundles:

```bash
pds4 bundle create --model flash-q2 --model qwen3-coder-q4 \
  --include-sources --include-runtime --signing-key LOCAL_ED25519_KEY \
  --signer operator --output /media/usb/pds4-pack

pds4 bundle verify /media/usb/pds4-pack --allowed-signers /etc/pds4/allowed_signers
sudo pds4 recover --bundle /media/usb/pds4-pack \
  --allowed-signers /etc/pds4/allowed_signers
```

Bundles include only artifacts permitted by their recorded redistribution
policy. Personal-only model weights require an explicit personal-use bundle;
unknown or metadata-only licenses omit weights.

## Installation and verification

`scripts/pds4-install` installs an immutable release without enabling or starting
services. It leaves any older DomesticLLM installation untouched as an external
rollback path. PDS4 itself uses `/srv/pds4`, `/var/lib/pds4`, `/var/cache/pds4`,
`/opt/pds4` and `/etc/pds4`.

```bash
sudo scripts/pds4-install
SKIP_MCP_RUNTIME=1 bash tests/run.sh
bash tests/offline/run.sh
```

The repository tests do not replace hardware validation. Release acceptance
requires the signed-bundle, two-A4500, KV, model-switch, reboot, rollback, soak
and no-egress matrix in [the offline runbook](docs/PDS4_OFFLINE_ACCEPTANCE.md).

## Pinned inputs and licensing

Exact upstream commits and model digests are recorded in `vendor.lock.json` and
the reviewed manifests under `models.d/`. PDS4 integration code is MIT licensed;
DS4, llama.cpp, Hermes, models, tokenizers and other artifacts retain their own
licenses and attribution. Technical ownership never overrides those terms.

PDS4 is built in the direct, inspectable spirit of Salvatore Sanfilippo's DS4:
one explicit working path, small dependencies, observable state and clear
failure instead of hidden fallback.
