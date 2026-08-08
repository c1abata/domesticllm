# PDS4 security review

## Executive summary

The repository review found and fixed one high-impact TOCTOU condition in model
import and one medium browser-secret persistence issue. No known Critical or
High finding remains open in the repository implementation. Hardware runtime,
driver, firewall and real offline-egress validation remain release gates.

## Resolved findings

### PDS4-SEC-001 — artifact replacement during privileged import

- Severity: High
- Location: `pds4/store.py:42-67`, `pds4/store.py:70-89`
- Evidence: import now rejects symlink/hardlink input, verifies the source, copies
  to a same-store temporary file, recomputes SHA-256 and size on that copy, and
  only then performs the atomic rename.
- Impact: before the fix, an unprivileged staging owner could race the verify and
  reopen operations and cause different bytes to enter a digest-named blob.
- Fix: destination-side digest verification immediately before `os.replace`.
- Mitigation: staging remains unprivileged and imported blobs become
  root-owned, group-readable and read-only.
- False-positive notes: none; a regression test simulates the file changing
  during the copy.

### PDS4-SEC-002 — browser persistence of the gateway bearer

- Severity: Medium
- Location: `web/app.js:9`, `web/app.js:46-79`
- Evidence: the bearer exists only in the module-local in-memory state and is
  inserted into request headers. No local/session storage, URL or DOM sink is
  used.
- Impact: storage persistence would increase exposure after reload and to any
  future same-origin script compromise.
- Fix: removed Web Storage and retained the secret only until reload/close.
- Mitigation: same-origin CSP, no third-party resources and text-only DOM APIs.
- False-positive notes: browser memory remains readable by a successful XSS;
  CSP and the absence of HTML/code sinks reduce that risk.

### PDS4-SEC-003 — unsafe offline bundle members

- Severity: High
- Location: `pds4/bundle.py:143-197`
- Evidence: verification rejects absolute/traversal paths, symlinks, hardlinks,
  special files, duplicates, undeclared files, checksum mismatch and unknown
  signatures before import or recovery.
- Impact: a malicious removable-media bundle could otherwise overwrite host
  paths or install substituted runtime code.
- Fix: closed inventory plus SHA-256 and Ed25519 SSH signature verification.
- Mitigation: import is data-only; runtime activation requires explicit
  `recover` after successful verification.
- False-positive notes: unsigned mode is exposed only as an internal function
  argument for isolated unit tests; the CLI requires allowed signers.

### PDS4-SEC-004 — model-controlled service switching

- Severity: High
- Location: `pds4/gateway.py:134-178`, `pds4/lane.py:109-165`
- Evidence: the gateway reads immutable control state and proxies only an active
  model. It has no systemd/control endpoint. Fast changes require the local
  locked CLI transaction, canary smoke test and rollback.
- Impact: an agent-generated model string cannot evict the active Fast model or
  affect Flash availability.
- Fix: strict data-plane/control-plane separation and explicit `warming` and
  `model_not_loaded` errors.
- Mitigation: gateway service has an empty capability set, closed device policy
  and read-only runtime/config paths.
- False-positive notes: local root remains the intended control-plane authority.

## Residual risks and required validation

- Direct gateway HTTP is appropriate only on an explicitly trusted LAN/tailnet;
  use SSH/WireGuard where transport interception is possible.
- DS4, CUDA, NVIDIA driver and llama.cpp behavior must be validated on the two
  RTX A4500 target with the signed artifacts actually deployed.
- `NO_UNEXPECTED_EGRESS` requires runtime socket monitoring on the isolated
  target; static unit policy and VM tests are necessary but not sufficient.
- Telegram and Hermes inherit their pinned upstream risk and must remain outside
  the inference server with least-privilege credentials and numeric allowlists.
