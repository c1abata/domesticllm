import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SovereigntyTests(unittest.TestCase):
    def test_offline_image_install(self):
        result = subprocess.run(["bash", "tests/offline/run.sh"], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_units_are_loopback_and_egress_denied(self):
        for name in ("pds4-flash.service", "pds4-flash-canary.service",
                     "pds4-fast@.service", "pds4-fast-canary@.service"):
            text = (ROOT / "systemd" / name).read_text()
            self.assertIn("127.0.0.1", text, name)
            self.assertIn("IPAddressDeny=any", text, name)
            self.assertIn("IPAddressAllow=localhost", text, name)
        gateway = (ROOT / "systemd/pds4-gateway.service").read_text()
        self.assertNotIn("systemctl", gateway)

    def test_models_and_generated_state_stay_out_of_git(self):
        ignore = (ROOT / ".gitignore").read_text()
        self.assertIn("models/**/*.gguf", ignore)
        self.assertIn("pds4-bundles/", ignore)

    def test_lan_gateway_configuration_is_explicit(self):
        source = (ROOT / "scripts/pds4-gateway-configure").read_text()
        self.assertIn("--allow-cidr", source)
        self.assertIn("ipaddress.ip_network", source)
        self.assertIn("IPAddressAllow=", source)
        base = (ROOT / "conf/pds4-gateway.env").read_text()
        self.assertIn("PDS4_GATEWAY_LISTEN=127.0.0.1", base)


if __name__ == "__main__":
    unittest.main()
