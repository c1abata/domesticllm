import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from pds4.bundle import PLATFORM, create, import_bundle, recover, verify
from pds4.common import Paths, PDS4Error
from pds4.store import import_model


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = Paths(self.root / "source-root")
        artifacts = self.root / "artifacts"
        artifacts.mkdir()
        gguf = artifacts / "tiny.gguf"
        gguf.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 1, 0) + b"bundle")
        digest = hashlib.sha256(gguf.read_bytes()).hexdigest()
        manifest = {
            "schema": 1, "id": "tiny-model", "family": "test", "purpose": "test",
            "source": {"repository": "local/test", "revision": "1" * 40},
            "artifacts": [{"file": "tiny.gguf", "role": "weights", "sha256": digest, "size": gguf.stat().st_size}],
            "runtime": {"engine": "llama.cpp", "commit": "2" * 40}, "lane": "fast",
            "context_tested": 128, "tools_allowed": False,
            "license": {"spdx": "MIT", "redistribution": "allowed"},
            "offline_ready": True, "status": "quarantine"
        }
        manifest_path = self.root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        import_model(manifest_path, artifacts, self.paths)

    def tearDown(self):
        self.temporary.cleanup()

    def test_create_verify_and_import_without_signature_for_unit_test(self):
        output = self.root / "bundle"
        create(output, ["tiny-model"], self.paths)
        verified = verify(output, require_signature=False)
        self.assertEqual(verified["platform"], PLATFORM)
        destination = Paths(self.root / "destination")
        self.assertEqual(import_bundle(output, destination, require_signature=False), ["tiny-model"])

    def test_tampered_payload_is_rejected(self):
        output = self.root / "bundle"
        create(output, ["tiny-model"], self.paths)
        artifact = output / "models/tiny-model/artifacts/tiny.gguf"
        artifact.chmod(0o640)
        artifact.write_bytes(artifact.read_bytes() + b"tamper")
        with self.assertRaises(PDS4Error):
            verify(output, require_signature=False)

    def test_recovery_installs_immutable_release(self):
        runtime = self.paths.at("/opt/pds4/releases/test")
        (runtime / "bin").mkdir(parents=True)
        (runtime / "bin/pds4-runtime").write_text("runtime", encoding="utf-8")
        current = self.paths.at("/opt/pds4/current")
        current.parent.mkdir(parents=True, exist_ok=True)
        current.symlink_to(runtime)
        output = self.root / "bundle"
        bundle = create(output, ["tiny-model"], self.paths, include_runtime=True)
        destination = Paths(self.root / "recovered")
        self.assertEqual(recover(output, destination, require_signature=False), bundle["id"])
        self.assertTrue(destination.at("/opt/pds4/current").is_symlink())


if __name__ == "__main__":
    unittest.main()
