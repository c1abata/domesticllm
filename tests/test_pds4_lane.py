import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pds4.common import Paths, PDS4Error
from pds4.lane import read_lane_state, switch_fast, write_lane_state


def manifest(model_id):
    return {
        "id": model_id, "lane": "fast", "context_tested": 16384,
        "artifacts": [{"role": "weights", "sha256": "a" * 64}],
    }


class LaneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = Paths(Path(self.temporary.name))
        self.actions = []

    def tearDown(self):
        self.temporary.cleanup()

    def runner(self, action, unit):
        self.actions.append((action, unit))

    def probe(self, port, model, key):
        self.actions.append(("probe", port, model))

    @mock.patch("pds4.lane._promote_manifest")
    @mock.patch("pds4.lane.verify_installed")
    def test_switch_uses_canary_then_primary(self, verify, promote):
        verify.return_value = manifest("qwen3-coder-q4")
        state = switch_fast("qwen3-coder-q4", self.paths, self.runner, self.probe)
        self.assertEqual(state["status"], "ready")
        self.assertEqual(self.actions[0], ("start", "pds4-fast-canary@qwen3-coder-q4.service"))
        self.assertIn(("probe", 8085, "qwen3-coder-q4"), self.actions)
        promote.assert_called_once()

    @mock.patch("pds4.lane.verify_installed")
    def test_failed_candidate_restores_previous(self, verify):
        verify.side_effect = lambda model_id, paths: manifest(model_id)
        write_lane_state(self.paths, "fast", "ready", "mistral-small-q4")

        def failing_probe(port, model, key):
            if model == "qwen3-coder-q4":
                raise PDS4Error("bad candidate")

        with self.assertRaises(PDS4Error):
            switch_fast("qwen3-coder-q4", self.paths, self.runner, failing_probe)
        self.assertEqual(read_lane_state(self.paths, "fast")["model"], "mistral-small-q4")
        self.assertIn(("start", "pds4-fast@mistral-small-q4.service"), self.actions)

    @mock.patch("pds4.lane.verify_installed")
    def test_flash_model_is_refused(self, verify):
        value = manifest("flash-q2")
        value["lane"] = "flash"
        verify.return_value = value
        with self.assertRaises(PDS4Error):
            switch_fast("flash-q2", self.paths, self.runner, self.probe)


if __name__ == "__main__":
    unittest.main()
