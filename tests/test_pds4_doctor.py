import tempfile
import unittest
from pathlib import Path

from pds4.common import Paths
from pds4.doctor import inspect


class DoctorTests(unittest.TestCase):
    def test_model_error_fails_overall_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gpu_map = root / "etc/pds4/gpus.conf"
            gpu_map.parent.mkdir(parents=True)
            gpu_map.write_text("PDS4_FLASH_GPU=GPU-a\n", encoding="utf-8")
            releases = root / "opt/pds4/releases/test"
            releases.mkdir(parents=True)
            (root / "opt/pds4/current").symlink_to(releases)
            model = root / "srv/pds4/models/broken"
            model.mkdir(parents=True)
            (model / "manifest.json").write_text("{}\n", encoding="utf-8")

            result = inspect(Paths(root))

            self.assertFalse(result["ok"])
            self.assertEqual(result["models"]["broken"], "PDS4Error")


if __name__ == "__main__":
    unittest.main()
