# Local AI operator contract

This repository deploys a narrow, local inference stack. Prefer plain C, Bash,
systemd, small reversible patches, explicit errors, and pinned dependencies.

## Mandatory workflow

`DISCOVER -> PLAN -> HUMAN_GATE -> PATCH -> VERIFY -> SECURITY_REVIEW -> CHECKPOINT`

- Read before editing. Keep each work unit path-scoped and reversible.
- Only one builder may modify files at a time.
- Scouts, verifiers, and security reviewers are read-only.
- Network access, downloads, package installation, `sudo`, service changes,
  firewall changes, deletion, publication, and remote operations require a
  human approval gate.
- A failed mutating operation may be retried without a new human gate only
  after recording its evidence, identifying and correcting the specific cause,
  and confirming that the target scope is unchanged and the retry is
  idempotent or reversible. Stop if the cause is unknown, scope expands, or a
  retry repeats the same failure.
- Never add an arbitrary-shell MCP tool or expose secrets in arguments/logs.
- Never run two huge model processes concurrently unless the operator approved
  the RAM/VRAM impact for that exact test.

## Release path

- DS4 native CUDA is a canary until correctness, two-GPU activity, stability,
  performance, and rollback gates pass.
- `llama.cpp` remains the fallback. Do not remove its working service path.
- Build only locked commits. Verify model SHA-256 before linking or starting it.
- CUDA target for RTX A4500 is explicit `sm_86`; do not silently use `native`.
- Native DS4 binds to loopback. Remote access is through an approved SSH or
  tailnet path, never an unauthenticated public listener.

## Verification

Run the smallest relevant checks first, then `tests/run.sh` on Linux/WSL.
Report exact commands, results, residual risk, and whether target-hardware
validation is still pending.
