from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except (ModuleNotFoundError, ImportError):
    ClientSession = StdioServerParameters = stdio_client = None


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "repo_inventory", "repo_read", "repo_search", "repo_diff", "check_run",
    "inference_health", "inference_smoke", "inference_benchmark", "ops_logs",
}


@unittest.skipIf(stdio_client is None, "locked MCP SDK is not installed")
class McpStdioContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_initialization_and_tool_allowlist(self) -> None:
        entrypoint = "local_ai_server.py" if os.name == "nt" else "locked_launcher.py"
        params = StdioServerParameters(
            command=sys.executable,
            args=["-B", str(ROOT / "mcp" / entrypoint)],
            cwd=str(ROOT),
            env={"LOCAL_AI_REPO_ROOT": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                tools = await session.list_tools()
        self.assertEqual({tool.name for tool in tools.tools}, EXPECTED)


if __name__ == "__main__":
    unittest.main()
