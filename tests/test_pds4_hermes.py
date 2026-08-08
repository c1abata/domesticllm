import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HermesBoundaryTests(unittest.TestCase):
    def test_server_units_have_no_telegram_secret(self):
        units = "\n".join(path.read_text() for path in (ROOT / "systemd").glob("pds4-*.service"))
        self.assertNotIn("TELEGRAM_BOT_TOKEN", units)
        self.assertNotIn("hermes", units.casefold())

    def test_tunnel_is_fail_fast_and_loopback_only(self):
        unit = (ROOT / "systemd/user/pds4-hermes-tunnel.service").read_text()
        self.assertIn("BatchMode=yes", unit)
        self.assertIn("ExitOnForwardFailure=yes", unit)
        self.assertIn("PDS4_LOCAL_BIND", unit)
        example = (ROOT / "examples/hermes/pds4-config.yaml").read_text()
        self.assertIn("http://127.0.0.1:18080/v1", example)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", example)

    def test_configurer_never_accepts_token_argument(self):
        script = (ROOT / "scripts/pds4-hermes-configure").read_text()
        self.assertNotIn("--token", script)
        self.assertIn("TELEGRAM_ALLOWED_USERS", script)


if __name__ == "__main__":
    unittest.main()
