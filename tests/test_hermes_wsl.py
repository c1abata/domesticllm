import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "28_configure_hermes_wsl.sh"


class HermesWSLTests(unittest.TestCase):
    def test_install_only_writes_narrow_private_configuration(self):
        with tempfile.TemporaryDirectory() as target:
            environment = os.environ.copy()
            environment["XDG_CONFIG_HOME"] = target
            result = subprocess.run(
                ["bash", str(SCRIPT), "--ssh-target", "operator@server-tailnet", "--install-only"],
                text=True, capture_output=True, env=environment, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            tunnel = pathlib.Path(target) / "domesticllm" / "tunnel.env"
            self.assertEqual(tunnel.stat().st_mode & 0o777, 0o600)
            self.assertIn("DOMESTICLLM_REMOTE_BIND=127.0.0.1:8080", tunnel.read_text())
            unit = pathlib.Path(target) / "systemd" / "user" / "domesticllm-hermes-tunnel.service"
            self.assertIn("ExitOnForwardFailure=yes", unit.read_text())

    def test_rejects_ssh_option_injection(self):
        with tempfile.TemporaryDirectory() as target:
            result = subprocess.run(
                ["bash", str(SCRIPT), "--ssh-target=-oProxyCommand=bad", "--install-only",
                 "--config-home", target],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
