import argparse
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

    def test_direct_mode_contract_is_supported_by_ds4(self):
        payload = TUI.build_payload("deepseek-v4-flash", "ciao", 1024, 0, "direct")
        self.assertEqual(payload["thinking"]["type"], "disabled")
        self.assertNotIn("reasoning_effort", payload)

    def test_thinking_mode_contract_is_supported_by_ds4(self):
        payload = TUI.build_payload("deepseek-v4-flash", "ciao", 2048, 0, "high")
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertNotIn("thinking", payload)

    def test_payload_preserves_multi_turn_history(self):
        messages = [{"role": "user", "content": "uno"},
                    {"role": "assistant", "content": "due"},
                    {"role": "user", "content": "tre"}]
        payload = TUI.build_payload("dolphin", "tre", 128, 0, "direct", messages)
        self.assertEqual(payload["messages"], messages)

    def test_clear_command_removes_history(self):
        args = argparse.Namespace(session="test", model="dolphin", max_tokens=128,
                                  reasoning="direct")
        messages = [{"role": "user", "content": "secret"}]
        handled, keep_going = TUI.chat_command("/clear", args, messages)
        self.assertTrue(handled)
        self.assertTrue(keep_going)
        self.assertEqual(messages, [])

    def test_history_trimming_keeps_complete_recent_turns(self):
        messages = [
            {"role": "user", "content": "a" * 900},
            {"role": "assistant", "content": "b" * 900},
            {"role": "user", "content": "recent question"},
            {"role": "assistant", "content": "recent answer"},
            {"role": "user", "content": "current question"},
        ]
        removed = TUI.trim_history(messages, context=400, max_tokens=100)
        self.assertEqual(removed, 1)
        self.assertEqual(messages[0]["content"], "recent question")
        self.assertEqual(messages[-1]["content"], "current question")

    def test_terminal_control_sequences_are_removed(self):
        self.assertEqual(TUI.terminal_safe("ok\x1b[31m\nnext\t"), "ok[31m\nnext\t")

    def test_api_key_file_must_not_be_public(self):
        with mock.patch.dict(os.environ, {"LOCAL_AI_API_KEY_FILE": str(SCRIPT)}, clear=True):
            with self.assertRaises(ValueError):
                TUI.load_key()


if __name__ == "__main__":
    unittest.main()
