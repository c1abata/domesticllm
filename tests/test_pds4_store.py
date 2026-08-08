import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pds4.common import Paths, PDS4Error
from pds4.manifest import validate_manifest
from pds4.store import import_model, verify_installed


class PDS4StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "input"
        self.artifacts.mkdir()
        self.gguf = self.artifacts / "tiny.gguf"
        self.gguf.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 1, 0) + b"payload")
        payload = self.gguf.read_bytes()
        self.manifest = {
            "schema": 1, "id": "tiny-model", "family": "test", "purpose": "test",
            "source": {"repository": "local/test", "revision": "1" * 40},
            "artifacts": [{"file": "tiny.gguf", "role": "weights", "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}],
            "runtime": {"engine": "llama.cpp", "commit": "2" * 40}, "lane": "fast",
            "context_tested": 128, "tools_allowed": False,
            "license": {"spdx": "MIT", "redistribution": "allowed"},
            "offline_ready": True, "status": "quarantine"
        }
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_import_is_content_addressed_and_verified(self):
        imported = import_model(self.manifest_path, self.artifacts, Paths(self.root))
        self.assertEqual(imported["status"], "verified")
        verified = verify_installed("tiny-model", Paths(self.root))
        self.assertEqual(verified["id"], "tiny-model")
        digest = self.manifest["artifacts"][0]["sha256"]
        self.assertTrue((self.root / "srv/pds4/store/sha256" / digest[:2] / digest[2:]).is_file())
        self.assertTrue((self.root / "srv/pds4/models/tiny-model/model.gguf").is_symlink())

    def test_rejects_checksum_mismatch(self):
        self.manifest["artifacts"][0]["sha256"] = "0" * 64
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaises(PDS4Error):
            import_model(self.manifest_path, self.artifacts, Paths(self.root))

    def test_rejects_symlink_artifact(self):
        real = self.gguf
        link = self.artifacts / "link.gguf"
        link.symlink_to(real)
        self.manifest["artifacts"][0]["file"] = "link.gguf"
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaises(PDS4Error):
            import_model(self.manifest_path, self.artifacts, Paths(self.root))

    def test_rejects_hardlinked_artifact(self):
        linked = self.artifacts / "hardlink.gguf"
        linked.hardlink_to(self.gguf)
        self.manifest["artifacts"][0]["file"] = "hardlink.gguf"
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaises(PDS4Error):
            import_model(self.manifest_path, self.artifacts, Paths(self.root))

    def test_detects_artifact_change_during_copy(self):
        expected = self.manifest["artifacts"][0]
        with mock.patch("pds4.store.sha256_file",
                        side_effect=[(expected["sha256"], expected["size"]), ("0" * 64, expected["size"]) ]):
            with self.assertRaises(PDS4Error):
                import_model(self.manifest_path, self.artifacts, Paths(self.root))

    def test_manifest_rejects_floating_revision(self):
        self.manifest["source"]["revision"] = "main"
        with self.assertRaises(PDS4Error):
            validate_manifest(self.manifest)


if __name__ == "__main__":
    unittest.main()
