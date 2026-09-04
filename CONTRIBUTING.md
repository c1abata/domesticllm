# Contributing

Contributions are welcome when they preserve the primary LAN console contract:
pinned inputs, explicit errors, one active backend, loopback-native inference
and a working rollback path.

1. Open an issue for material architecture or dependency changes.
2. Create a focused branch and keep patches path-scoped.
3. Do not commit model weights, secrets, host inventories, benchmark prompts,
   or generated evidence.
4. Run the tests relevant to the changed component; run
   `SKIP_MCP_RUNTIME=1 bash tests/run.sh` for repository-wide changes.
5. Describe target hardware validation separately from local/static tests.
6. Keep optional audio, video, MCP and recovery work isolated from the primary
   gateway unless an explicit resource-arbitration design is included.

Changes involving network access, installation, sudo, services, firewall,
deletion, or publication require explicit operator approval. Security-sensitive
changes should include abuse cases and negative tests.
