import json
import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryPolicyTests(unittest.TestCase):
    def test_vendor_lock_matches_shell_refs(self):
        lock = json.loads((ROOT / "vendor.lock.json").read_text(encoding="utf-8"))
        shell = (ROOT / "conf/vendor-refs.env").read_text(encoding="utf-8")
        values = dict(
            line.split("=", 1)
            for line in shell.splitlines()
            if line and not line.startswith("#") and "=" in line
        )
        self.assertEqual(values["DS4_COMMIT"], lock["sources"]["ds4"]["commit"])
        self.assertEqual(values["LLAMA_COMMIT"], lock["sources"]["llama_cpp"]["commit"])
        self.assertEqual(
            values["DS4_Q2_IMATRIX_SHA256"],
            lock["models"]["deepseek_v4_flash_q2_imatrix"]["sha256"],
        )
        uncensored = lock["models"]["deepseek_v4_flash_abliterated_q2"]
        self.assertEqual(values["DS4_UNCENSORED_Q2_REVISION"], uncensored["revision"])
        self.assertEqual(values["DS4_UNCENSORED_Q2_SHA256"], uncensored["sha256"])
        self.assertEqual(values["DS4_UNCENSORED_Q2_FILE"], uncensored["filename"])

    def test_no_floating_or_dynamic_supply_chain_in_critical_scripts(self):
        critical = [
            "10_install_llamacpp_cpu.sh",
            "11_install_ds4_cpu_reference.sh",
            "12_install_llamacpp_cuda.sh",
            "13_install_ds4_cuda_reference.sh",
            "20_install_antirez_tools.sh",
            "32_fetch_ds4_flash_gguf.sh",
        ]
        combined = "\n".join(
            (ROOT / "scripts" / name).read_text(encoding="utf-8") for name in critical
        )
        self.assertNotRegex(combined, r"\bgit\s+pull\b")
        self.assertNotIn("resolve/main/", combined)
        self.assertNotIn("npx -y", combined)
        self.assertIn("sha256sum", combined)

    def test_repl_has_no_shell_execution(self):
        repl = (ROOT / "src/localai-repl.c").read_text(encoding="utf-8")
        self.assertNotRegex(repl, r"\bsystem\s*\(")
        self.assertIn("curl_easy_perform", repl)

    def test_service_keys_are_file_backed_and_runtime_is_read_only(self):
        for unit in (ROOT / "systemd").glob("*.service"):
            text = unit.read_text(encoding="utf-8")
            if "llama-server" not in text:
                continue
            self.assertIn("--api-key-file", text, unit.name)
            self.assertNotIn("--api-key ${", text, unit.name)
            self.assertIn("ProtectSystem=strict", text, unit.name)
            self.assertNotRegex(text, r"ReadWritePaths=.*?/opt/local-ai")

    def test_default_service_profiles_are_loopback_only(self):
        for env_file in (ROOT / "conf").glob("local-ai*.env"):
            text = env_file.read_text(encoding="utf-8")
            if "LOCAL_AI_HOST=" in text:
                self.assertIn("LOCAL_AI_HOST=127.0.0.1", text, env_file.name)
            self.assertNotIn("CHANGE_ME", text, env_file.name)

    def test_incomplete_models_are_only_in_quarantine(self):
        model_root = ROOT / "models"
        for item in model_root.rglob("*"):
            if item.is_file() and (item.name.endswith(".part") or ".bad." in item.name):
                self.assertIn("quarantine", item.parts)

    def test_agent_gate_is_persistent(self):
        policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("DISCOVER -> PLAN -> HUMAN_GATE -> PATCH", policy)
        self.assertIn("Only one builder", policy)

    def test_codex_mcp_and_agent_controls(self):
        config = tomllib.loads((ROOT / ".codex/config.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["agents"]["max_threads"], 4)
        self.assertEqual(config["agents"]["max_depth"], 1)
        self.assertNotIn("ops_executor", config["agents"])
        expected = {
            "repo_inventory", "repo_read", "repo_search", "repo_diff", "check_run",
            "inference_health", "inference_smoke", "inference_benchmark", "ops_logs",
        }
        self.assertEqual(set(config["mcp_servers"]["local_ai"]["enabled_tools"]), expected)
        self.assertEqual(config["mcp_servers"]["local_ai"]["default_tools_approval_mode"], "prompt")

        active = ROOT / ".codex/agents"
        for profile in active.glob("*.toml"):
            role = tomllib.loads(profile.read_text(encoding="utf-8"))
            if role["name"] == "builder":
                self.assertEqual(role["sandbox_mode"], "workspace-write")
                self.assertFalse(role["sandbox_workspace_write"]["network_access"])
            else:
                self.assertEqual(role["sandbox_mode"], "read-only")
        disabled = tomllib.loads(
            (ROOT / ".codex/disabled-agents/ops-executor.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(disabled["name"], "ops_executor")
        self.assertEqual(disabled["sandbox_mode"], "read-only")

    def test_secret_and_optional_download_policy(self):
        installers = "\n".join(
            (ROOT / "scripts" / name).read_text(encoding="utf-8")
            for name in ("90_install_ds4_intel_stack.sh", "90_install_ds4_nvidia_stack.sh")
        )
        self.assertNotIn("--api-key", installers)
        optional = (ROOT / "scripts/33_fetch_hf_gguf.sh").read_text(encoding="utf-8")
        self.assertNotIn("resolve/main", optional)
        self.assertIn("disabled by supply-chain policy", optional)

    def test_security_review_regressions(self):
        client_scripts = "\n".join(
            (ROOT / "scripts" / name).read_text(encoding="utf-8")
            for name in ("50_ask.sh", "60_slot_save.sh", "61_slot_restore.sh", "62_slot_erase.sh")
        )
        self.assertNotIn('Authorization: Bearer $KEY', client_scripts)
        self.assertIn("curl_with_bearer", client_scripts)

        ownership_scripts = "\n".join(
            (ROOT / "scripts" / name).read_text(encoding="utf-8")
            for name in ("00_install_base.sh", "05_prepare_ubuntu_server.sh", "21_build_local_repl.sh")
        )
        self.assertNotRegex(ownership_scripts, r"chown\s+-R\s+localai.*LOCAL_AI_HOME")
        self.assertIn("localai-build", ownership_scripts)

        tools = (ROOT / "scripts/20_install_antirez_tools.sh").read_text(encoding="utf-8")
        self.assertNotIn("find ", tools)
        self.assertIn("deepseek4-quantize", tools)

        fetch = (ROOT / "scripts/32_fetch_ds4_flash_gguf.sh").read_text(encoding="utf-8")
        self.assertIn("The locked q2 SHA-256 cannot be overridden", fetch)
        self.assertIn("ds4flash-uncensored.gguf", fetch)
        for installer_name in (
            "90_install_ds4_intel_stack.sh", "90_install_ds4_nvidia_stack.sh"
        ):
            installer = (ROOT / "scripts" / installer_name).read_text(encoding="utf-8")
            self.assertIn("uncensored-q2", installer)
            self.assertIn('request_model="ds4flash-uncensored"', installer)
        self.assertIn("DS4_DOWNLOAD_WORKER=1", fetch)

        install = (ROOT / "scripts/15_install_ds4_native.sh").read_text(encoding="utf-8")
        self.assertIn("canary health failed and was disabled", install)

        config = tomllib.loads((ROOT / ".codex/config.toml").read_text(encoding="utf-8"))
        mcp = config["mcp_servers"]["local_ai"]
        self.assertIn(mcp["command"], {"wsl.exe", ".venv-mcp/bin/python"})
        if mcp["command"] == "wsl.exe":
            self.assertIn(".venv-mcp/bin/python", mcp["args"])
        else:
            self.assertEqual(mcp["command"], ".venv-mcp/bin/python")
        self.assertIn("mcp/locked_launcher.py", mcp["args"])

    def test_lan_gateway_requires_explicit_network_scope(self):
        unit = (ROOT / "systemd/domesticllm-lan-gateway.service").read_text(encoding="utf-8")
        installer = (ROOT / "scripts/21_install_lan_gateway.sh").read_text(encoding="utf-8")
        launcher = (ROOT / "scripts/domesticllm-lan").read_text(encoding="utf-8")
        self.assertIn("IPAddressDeny=any", unit)
        self.assertIn("IPAddressAllow=localhost", unit)
        self.assertIn("--lan-cidr", installer)
        self.assertIn("ipaddress.ip_network", installer)
        self.assertIn("IPAddressAllow=%s", installer)
        self.assertNotRegex(launcher, r"10\.\d+\.\d+\.\d+")
        self.assertIn("DOMESTICLLM_LAN_HOST", launcher)


if __name__ == "__main__":
    unittest.main()
