#!/usr/bin/env bash
set -euo pipefail
IFACE="${1:?Usage: $0 IFACE}"
ethtool "$IFACE" | grep -E 'Speed|Duplex|Auto-negotiation|Link detected' || true
ip -s link show "$IFACE"
