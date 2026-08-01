# Security policy

## Supported version

Security fixes are applied to the latest revision of the default branch.
Pinned upstream revisions remain unchanged until an explicit, tested update.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open a
public issue for API-key disclosure, command execution, authentication bypass,
unsafe service permissions, or dependency-compromise reports.

Include affected revision, deployment profile, reproduction steps, impact, and
suggested mitigation when available. Never include real keys, prompts, model
data, host inventories, or private addresses in the report.

## Deployment boundary

- Native DS4 must remain on loopback.
- The LAN gateway requires bearer authentication and an explicit CIDR allowlist.
- Direct LAN HTTP is suitable only for a trusted network. Prefer TLS or an SSH
  tunnel where interception is possible.
- Model-generated code and tool calls are untrusted input. Run them with least
  privilege and require human approval for mutations.
- Never publish GGUF files, API keys, runtime environment files, soak evidence,
  or host-specific checkpoints.
