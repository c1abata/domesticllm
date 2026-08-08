import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pds4.benchmark import plan, record
from pds4.common import Paths


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    @mock.patch("pds4.benchmark.verify_installed")
    def test_record_contains_identity_but_not_prompt(self, verify):
        verify.return_value = {
            "lane": "fast", "runtime": {"engine": "llama.cpp", "commit": "b" * 40},
            "artifacts": [{"role": "weights", "sha256": "a" * 64}],
        }
        output = self.root / "result.json"
        result = record(Paths(self.root), "qwen3-coder-q4", b"secret prompt",
                        [{"ttft_ms": 100}], [{"uuid": "GPU-test"}], output)
        self.assertNotIn("secret prompt", output.read_text())
        self.assertEqual(result["runtime_commit"], "b" * 40)
        self.assertIn("prompt_sha256", result)

    def test_plan_keeps_large_context_hardware_gated(self):
        matrix = plan()
        self.assertEqual(matrix["flash"][0]["context"], 32768)
        self.assertEqual(matrix["flash"][-1]["status"], "soak-gated")
        self.assertEqual(matrix["cpu_partial_offload"]["status"], "experimental")


if __name__ == "__main__":
    unittest.main()
