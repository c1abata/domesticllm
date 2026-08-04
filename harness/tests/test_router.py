from pathlib import Path
import unittest

from domestic_harness.config import HarnessConfig, ModelProfile
from domestic_harness.router import Router


def profile(name: str, capabilities: set[str]) -> ModelProfile:
    return ModelProfile(
        name=name,
        base_url="http://127.0.0.1:8080",
        model=name,
        api_key_env="TEST_KEY",
        capabilities=frozenset(capabilities),
    )


class RouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = HarnessConfig(
            default_profile="general",
            state_dir=Path("/tmp/domesticllm-harness-test"),
            max_history_messages=12,
            profiles={
                "qwen": profile("qwen", {"code"}),
                "deepseek": profile("deepseek", {"reasoning"}),
                "security": profile("security", {"security"}),
                "general": profile("general", {"general"}),
            },
        )
        self.router = Router(self.config)

    def test_code_route(self) -> None:
        self.assertEqual(self.router.choose("correggi questo codice Python").profile.name, "qwen")

    def test_reasoning_route(self) -> None:
        self.assertEqual(self.router.choose("analizza questa architettura").profile.name, "deepseek")

    def test_security_route(self) -> None:
        self.assertEqual(self.router.choose("valuta hardening e firewall").profile.name, "security")

    def test_explicit_profile_wins(self) -> None:
        self.assertEqual(self.router.choose("codice Python", "deepseek").profile.name, "deepseek")

    def test_unknown_profile_fails(self) -> None:
        with self.assertRaises(ValueError):
            self.router.choose("ciao", "missing")


if __name__ == "__main__":
    unittest.main()
