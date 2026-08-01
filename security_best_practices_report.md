# Security review: domesticLLM DS4 stack

## Executive summary

No critical or high-severity finding was identified in the production DS4 and
llama fallback paths. Both bind to loopback, run without privileges, use
root-owned immutable releases/models, and restrict systemd networking and
devices. Secrets are read from permission-controlled files and are not placed
in generated client configuration or process arguments by the supplied client.

The security skill has no general Python CLI reference; this review therefore
uses repository policy, stdlib threat surfaces, systemd isolation and direct
code inspection as its concrete baseline.

## Medium severity

### SEC-04: LAN bearer authentication uses HTTP

Impact: a machine capable of intercepting traffic on the trusted LAN could
capture and replay the gateway bearer token.

Mitigation in place: the listener is restricted by the systemd IP policy to
the operator-approved LAN CIDR, requests require a high-entropy token, anonymous access is
rejected, secrets are mode 0600/0640, and DS4 itself remains on loopback. Use
the existing SSH tunnel instead on an untrusted or shared network; TLS remains
the next hardening step for the direct LAN profile.

## Low severity and accepted residual risks

### SEC-01: DS4 has no native API authentication

Impact: a local process able to connect to loopback can invoke inference.

Mitigation in place: `local-ai-ds4-native.service` binds to `127.0.0.1`, uses
`IPAddressDeny=any` plus `IPAddressAllow=localhost`, and exposes no LAN socket.
Remote use must pass through an approved SSH/tailnet tunnel. This is accepted
for the narrow local deployment.

### SEC-02: Optional steering vectors can alter model behavior

Impact: an unreviewed vector could reduce correctness or bias responses.

Mitigation in place: the installed verbosity vector is sourced from the exact
locked DS4 commit, checked for the required 43x4096 f32 size and recorded by
SHA-256. Steering is not enabled in the default production service and must be
tested as a separate loopback canary.

### SEC-03: Build-time upstream test fixtures may use network/Git-LFS

Impact: a broad upstream `ctest` can fetch mutable test data and is not a fully
offline reproducibility proof.

Mitigation in place: production revisions are pinned; DS4 build tests are
model-independent and offline; model hashes are checked before startup. The
llama production build disables curl and WebUI assets. Target-model canaries,
not downloaded tokenizer fixtures, are the release gate.

## Positive controls verified

- No arbitrary-shell MCP tool; MCP subprocess execution uses a fixed allowlist.
- MCP paths deny secret/config directories and redact credentials and prompts.
- Production services use `NoNewPrivileges`, strict filesystem protection,
  empty capability sets, explicit NVIDIA device allowlists and loopback-only
  address policy.
- Model and release files are root-owned and not group/world writable.
- API keys remain in root/localai-readable files; clients pass authorization by
  curl configuration on stdin rather than command-line arguments.
- The streaming TUI rejects URL credentials/query strings, rejects symlinked or
  overly permissive API-key files, and strips terminal control bytes before
  rendering model-controlled text on an interactive terminal.
- The LAN gateway has a fixed loopback backend, route and body-size allowlists,
  constant-time bearer comparison, single-request backpressure and no request
  body or authorization logging. Anonymous access was verified to return 401.
- Huge-model tests are sequential; GPU1 remains isolated from DS4.
- Fallback and DS4 releases remain independently selectable and rollback-tested.

## Completed operational requirement

The temporary passwordless sudo policy was removed after soak, cleanup and the
final checkpoint. `sudo -n true` fails, while DS4 inference remains operable
through its normal service account.
