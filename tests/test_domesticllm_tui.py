import importlib.util
import os
import pathlib
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "domesticllm-tui.py"
SPEC = importlib.util.spec_from_file_location("domesticllm_tui", SCRIPT)
TUI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TUI)


class DomesticLlmTuiTests(unittest.TestCase):
    def test_loopback_url_is_accepted(self):
        parsed = TUI.validate_url("http://127.0.0.1:8083/v1/chat/completions")
        self.assertEqual(parsed.port, 8083)

    def test_url_rejects_embedded_credentials_and_query(self):
        for url in ("http://user:key@127.0.0.1:8083/v1", "http://127.0.0.1/v1?key=x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                TUI.validate_url(url)

    def test_api_key_rejects_header_injection(self):
        with mock.patch.dict(os.environ, {"LOCAL_AI_API_KEY": "good\nInjected: yes"}, clear=True):
            with self.assertRaises(ValueError):
                TUI.load_key()

    def test_positive_integer_validation(self):
        self.assertEqual(TUI.positive_int("100000"), 100000)
        with self.assertRaises(Exception):
            TUI.positive_int("0")

    def test_terminal_control_sequences_are_removed(self):
        self.assertEqual(TUI.terminal_safe("ok\x1b[31m\nnext\t"), "ok[31m\nnext\t")

    def test_api_key_file_must_not_be_public(self):
        with mock.patch.dict(os.environ, {"LOCAL_AI_API_KEY_FILE": str(SCRIPT)}, clear=True):
            with self.assertRaises(ValueError):
                TUI.load_key()


if __name__ == "__main__":
    unittest.main()
