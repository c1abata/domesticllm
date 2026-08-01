from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SERVER_PATH = Path(__file__).resolve().parents[1] / "mcp" / "local_ai_server.py"
SPEC = importlib.util.spec_from_file_location("local_ai_mcp_server", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
MCP_IMPORT_ERROR = ""
try:
    SPEC.loader.exec_module(server)
except ModuleNotFoundError as exc:
    if exc.name != "mcp" and not (exc.name or "").startswith("mcp."):
        raise
    MCP_IMPORT_ERROR = str(exc)
    server = None


@unittest.skipIf(server is None, f"locked MCP SDK is not installed: {MCP_IMPORT_ERROR}")
class RepositoryToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.joinpath("src").mkdir()
        self.root.joinpath("src", "ok.txt").write_bytes(b"alpha\nbeta\n")
        self.root.joinpath(".git").mkdir()
        self.root.joinpath(".git", "config").write_text("secret", encoding="utf-8")
        self.root.joinpath(".env").write_text("TOKEN=bad", encoding="utf-8")
        self.original_root = server.REPO_ROOT
        server.REPO_ROOT = self.root

    def tearDown(self) -> None:
        server.REPO_ROOT = self.original_root
        self.temp.cleanup()

    def test_uniform_result_and_read(self) -> None:
        result = server.repo_read("src/ok.txt")
        self.assertEqual(set(result), {"ok", "summary", "evidence", "artifacts", "next_gate"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence"][0]["content"], "alpha\nbeta\n")

    def test_path_escape_and_sensitive_paths_are_rejected(self) -> None:
        self.assertFalse(server.repo_read("../outside.txt")["ok"])
        self.assertFalse(server.repo_read(".git/config")["ok"])
        self.assertFalse(server.repo_read(".env")["ok"])

    def test_inventory_and_search_skip_sensitive_files(self) -> None:
        paths = {entry["path"] for entry in server.repo_inventory()["evidence"]}
        self.assertEqual(paths, {"src/ok.txt"})
        result = server.repo_search("beta")
        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence"][0]["line"], 2)


@unittest.skipIf(server is None, f"locked MCP SDK is not installed: {MCP_IMPORT_ERROR}")
class PolicyTests(unittest.TestCase):
    def test_only_expected_tools_are_registered(self) -> None:
        names = {tool.name for tool in asyncio.run(server.SERVER.list_tools())}
        self.assertEqual(names, {
            "repo_inventory", "repo_read", "repo_search", "repo_diff", "check_run",
            "inference_health", "inference_smoke", "inference_benchmark", "ops_logs",
        })

    def test_check_catalog_rejects_arbitrary_input(self) -> None:
        result = server.check_run("shell:curl example.invalid")
        self.assertFalse(result["ok"])
        self.assertIn("unknown check_id", result["summary"])

    def test_backend_rejects_non_loopback_and_credentials(self) -> None:
        with mock.patch.dict(server.os.environ, {"LOCAL_AI_DS4_URL": "http://192.168.1.2:8083"}):
            with self.assertRaises(ValueError):
                server._backend_url("ds4")
        with mock.patch.dict(server.os.environ,
                             {"LOCAL_AI_DS4_URL": "http://user:key@127.0.0.1:8083"}):
            with self.assertRaises(ValueError):
                server._backend_url("ds4")

    def test_log_redaction_covers_prompts_tokens_and_secrets(self) -> None:
        raw = 'safe\n{"prompt":"private"}\nSENTINEL_VALUE\nAuthorization: Bearer abc\napi_key=xyz\ntokens=99'
        redacted = server._redact(raw)
        self.assertIn("safe", redacted)
        for secret in ("private", "SENTINEL_VALUE", "abc", "xyz", "99"):
            self.assertNotIn(secret, redacted)

    def test_ops_logs_is_unit_and_line_bounded(self) -> None:
        self.assertFalse(server.ops_logs("../../etc/passwd")["ok"])
        self.assertFalse(server.ops_logs("ds4-canary", 501)["ok"])
        done = subprocess.CompletedProcess(args=[], returncode=0,
                                           stdout="safe\nprompt=hidden\n", stderr="")
        with mock.patch.object(server, "_run_fixed", return_value=done) as run:
            result = server.ops_logs("ds4-canary", 20)
        self.assertTrue(result["ok"])
        self.assertNotIn("hidden", json.dumps(result))
        command = run.call_args.args[0]
        self.assertIn("local-ai-ds4-native.service", command)
        self.assertNotIn("ds4-canary", command)


class SourcePolicyTests(unittest.TestCase):
    def test_source_and_lock_declare_bounded_server(self) -> None:
        source = SERVER_PATH.read_text(encoding="utf-8")
        names = set(__import__("re").findall(r"^def (repo_inventory|repo_read|repo_search|repo_diff|check_run|inference_health|inference_smoke|inference_benchmark|ops_logs)\(", source, __import__("re").M))
        self.assertEqual(len(names), 9)
        self.assertNotIn("shell=True", source)
        lock = SERVER_PATH.with_name("requirements.lock").read_text(encoding="utf-8")
        self.assertIn("mcp==1.28.1 --hash=sha256:", lock)
        launcher = SERVER_PATH.with_name("locked_launcher.py").read_text(encoding="utf-8")
        self.assertIn("requirements.lock", launcher)
        self.assertIn("expected {expected}, got {actual}", launcher)


if __name__ == "__main__":
    unittest.main()
