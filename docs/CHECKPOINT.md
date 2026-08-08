# Current checkpoint

Date: 2026-08-08.

## Repository outcome

- DS4 `ds4f-mxfp4` canary pinned at
  `80df56af4070d0fc62f6f9682b1854f8e5be8b00`.
- RTX A4500 production decision remains q2-imatrix; MXFP4 CUDA is gated as
  unsupported at this revision.
- Offline build includes the upstream scalar MXFP4 dot-product regression.
- Native resident sessions are explicit and default to the validated value 1.
- Authenticated gateway serves a zero-dependency Web UI, aggregates the live
  DS4/fast model catalog, and routes only allowlisted fast model IDs.
- WSL Hermes examples and a fail-fast SSH user-tunnel installer are present.
- Telegram uses Hermes' native deny-by-default allowlist path; botlib is a
  pinned design reference only.

## Verification evidence

```text
SKIP_MCP_RUNTIME=1 tests/run.sh
52 tests passed; 9 dynamic MCP tests skipped
bash syntax: pass
shellcheck: pass
DS4 runtime policy: pass
systemd system-unit syntax: pass (target executables absent on WSL)
git diff --check: pass
node --check web/app.js: pass
```

Real-browser smoke validation is pending: Playwright CLI was available, but the
host has no Chrome/Chromium distribution and requested a separate browser
download. No package was installed without an operator gate.

The tests ran on Ubuntu/WSL, Intel Core i5-13420H, 14 GiB visible RAM, without
`nvidia-smi`. They validate repository behavior, not CUDA/model performance.

## Security review

- Model services remain loopback-only; the base gateway unit allows only
  localhost and the installer adds exactly the operator-approved CIDR.
- API requests require a constant-time bearer check. Browser assets contain no
  secret, enforce same-origin CSP/resource isolation, avoid HTML injection, and
  keep the key only in tab-scoped session storage.
- The gateway exposes no service-control route. Model switching is data-plane
  routing to an already-running fixed backend.
- Hermes secrets stay in a mode-0600 environment file; SSH uses batch mode,
  fail-fast forwarding and a fixed local/remote bind generated from validated
  inputs. Telegram requires an explicit numeric user allowlist.

## Pending target gates

1. Build the new DS4 commit with CUDA `sm_86` on the Ryzen 9 5950X workstation.
2. Verify the locked q2 model SHA-256 before startup.
3. Run correctness, tool calling, GPU isolation, performance and rollback
   acceptance against the previous release.
4. Complete the four-hour mixed-request soak.
5. Test two resident sessions separately before changing the default from one.
6. With operator approval, install/restart the gateway and configure the WSL
   tunnel, Hermes and Telegram credentials.
