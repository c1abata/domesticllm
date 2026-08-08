import hashlib
import tempfile
import unittest
from pathlib import Path

from pds4.cache import checkpoint, parse_size, register, restore, verify_checkpoint
from pds4.common import Paths, PDS4Error


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = Paths(Path(self.temporary.name))
        self.identity = {
            "model_sha256": "a" * 64, "runtime_commit": "b" * 40,
            "tokenizer_fingerprint": "c" * 64, "chat_template_fingerprint": "d" * 64,
            "context": 32768, "kv_format": "ds4-v1", "kv_quantization": "q8_0",
            "steering_fingerprint": "0" * 64, "session_id": "session-1", "lane": "flash",
            "model_id": "flash-q2",
        }
        register(self.paths, self.identity)
        live = self.paths.at("/run/pds4/sessions/session-1")
        live.mkdir(parents=True)
        (live / "payload.kv").write_bytes(b"persistent kv")

    def tearDown(self):
        self.temporary.cleanup()

    def test_checkpoint_verify_restore(self):
        metadata = checkpoint(self.paths, "session-1")
        self.assertEqual(metadata["payload_sha256"], hashlib.sha256(b"persistent kv").hexdigest())
        live = self.paths.at("/run/pds4/sessions/session-1/payload.kv")
        live.unlink()
        self.assertEqual(restore(self.paths, "session-1").read_bytes(), b"persistent kv")

    def test_identity_change_invalidates_checkpoint(self):
        checkpoint(self.paths, "session-1")
        changed = dict(self.identity)
        changed["context"] = 65536
        register(self.paths, changed)
        with self.assertRaises(PDS4Error):
            verify_checkpoint(self.paths, "session-1")

    def test_corrupt_payload_is_rejected(self):
        metadata = checkpoint(self.paths, "session-1")
        target = self.paths.at("/var/cache/pds4/kv/flash/session-1/payload.kv")
        target.write_bytes(b"corrupt")
        with self.assertRaises(PDS4Error):
            verify_checkpoint(self.paths, "session-1")

    def test_size_parser(self):
        self.assertEqual(parse_size("64G"), 64 * 1024 ** 3)
        with self.assertRaises(PDS4Error):
            parse_size("0G")


if __name__ == "__main__":
    unittest.main()
