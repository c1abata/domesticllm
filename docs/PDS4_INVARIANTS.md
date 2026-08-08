# PDS4 invariants

PDS4 owns a local, inspectable and recoverable inference lifecycle. These rules
are release gates, not preferences.

1. Build and startup never download data.
2. Production inputs use exact commits and SHA-256 digests; floating references are refused.
3. Models are untrusted data and are never imported as executable code.
4. Model weights stay outside Git in the content-addressed store.
5. DS4 and llama.cpp bind to loopback and have no WAN egress.
6. Flash and Fast have independent GPU assignments by UUID.
7. Fast switching is explicit, canary-tested and reversible; agents cannot trigger it through the API.
8. CLI, TUI, Web UI and LAN API work without WAN, DNS or cloud accounts.
9. Releases, source bundles, toolchains and licensed artifacts can be recovered offline.
10. Telegram is optional and is the only component allowed to require an external service.

Licenses remain authoritative. A verified artifact is technically usable; it
is not automatically redistributable or promoted.
