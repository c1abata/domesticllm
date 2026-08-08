# Hermes and Telegram boundary

Hermes is an optional client. It is not part of either inference lane and the
PDS4 server never needs a Telegram token.

The baseline path is a user-owned SSH tunnel from WSL to the PDS4 gateway:

```text
Hermes/Telegram (WSL, WAN allowed) -> 127.0.0.1:18080
SSH tunnel                         -> server 127.0.0.1:8080
PDS4 gateway and runtimes          -> no WAN egress
```

Install the reviewed, pinned Hermes release from the offline bundle, then run
`pds4-hermes-configure --ssh-target USER@HOST`. Review the generated files
before enabling the user tunnel. Copy the gateway key and Telegram token to
`~/.hermes/.env` with mode `0600`; require a numeric `TELEGRAM_ALLOWED_USERS`.

When WAN is unavailable, only the Telegram adapter is offline. CLI, TUI, Web,
LAN API, SSH and local Hermes continue to work. WireGuard, Headscale and
Tailscale are optional transports, not core dependencies.
