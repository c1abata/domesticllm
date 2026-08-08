# Offline sovereignty acceptance

Run this gate only on the Ubuntu 24.04 A4500 target after creating and signing a
complete personal bundle. Physically disconnect WAN or apply the reviewed lab
isolation, disable DNS, then confirm both are unreachable before setting
`PDS4_WAN_DISABLED=1`.

On a clean host, first run the signed bundle's `bootstrap/scripts/pds4-install`;
then use the installed `pds4 bundle verify` and `pds4 recover` commands. The
bootstrap is part of the closed bundle inventory and is never taken from WAN.

The pre-reboot harness verifies the bundle, doctor state, both lanes, Fast
switch and rollback. Operators must additionally rebuild both pinned source
bundles with `pds4-offline-build`, chat through CLI/TUI/LAN API, checkpoint and
restore KV, and capture socket monitoring evidence. After reboot, run the
post-reboot phase and repeat both chats.

The release record is complete only with this exact matrix:

```text
OFFLINE_BUILD=pass
OFFLINE_INSTALL=pass
FLASH_LANE=pass
FAST_LANE=pass
LAN_API=pass
TUI=pass
KV_RESTORE=pass
MODEL_SWITCH=pass
REBOOT_RECOVERY=pass
ROLLBACK=pass
NO_UNEXPECTED_EGRESS=pass
```

Missing entries are pending, never implied passes. Repository/VM tests do not
substitute for the two-A4500 correctness, performance and four-hour soak gates.
