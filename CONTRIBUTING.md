# Contributing

Contributions are welcome when they preserve DomesticLLM's narrow operational
contract: pinned inputs, explicit errors, reversible installs, loopback-native
inference, and a working fallback.

1. Open an issue for material architecture or dependency changes.
2. Create a focused branch and keep patches path-scoped.
3. Do not commit model weights, secrets, host inventories, benchmark prompts,
   or generated evidence.
4. Run `SKIP_MCP_RUNTIME=1 bash tests/run.sh` on Linux.
5. Describe target hardware validation separately from local/static tests.

Changes involving network access, installation, sudo, services, firewall,
deletion, or publication require explicit operator approval. Security-sensitive
changes should include abuse cases and negative tests.
