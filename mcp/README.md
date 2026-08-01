# Local AI MCP

Stdio server based on `mcp==1.28.1`. It exposes only bounded repository reads,
fixed checks, loopback inference probes, and redacted allowlisted journal reads.
There is no arbitrary shell, generic network, write, delete, sudo, home, secret,
or `.git` write interface.

The dependency lock targets Ubuntu 24.04 x86_64 with CPython 3.12:

```bash
python3 -m venv .venv-mcp
.venv-mcp/bin/python -m pip install --require-hashes -r mcp/requirements.lock
.venv-mcp/bin/python mcp/local_ai_server.py
```

Installation is intentionally not automated and requires a human gate. Point
Codex at the reviewed virtualenv interpreter in production.

The active project `.codex/config.toml` starts this Linux venv through `wsl.exe`
because this checkout is controlled by Codex desktop on Windows. On the native
Ubuntu target, set `command = ".venv-mcp/bin/python"` and remove that interpreter
from `args`. `locked_launcher.py` compares every installed package version with
the hash lock before serving.

Inference overrides `LOCAL_AI_DS4_URL` and `LOCAL_AI_LLAMA_URL` are accepted
only for unauthenticated loopback HTTP on ports 8082-8084.
