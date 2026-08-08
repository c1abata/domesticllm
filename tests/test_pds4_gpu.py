import tempfile
import unittest
from pathlib import Path

from pds4.common import Paths, PDS4Error
from pds4.gpu import GPU, assign


class GPUAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.gpus = [
            GPU("GPU-flash", 1, "0000:01:00.0", 20470, "8.6"),
            GPU("GPU-fast", 0, "0000:02:00.0", 20470, "8.6"),
        ]

    def tearDown(self):
        self.temporary.cleanup()

    def test_assignment_uses_uuid_and_host_device_node(self):
        assign("GPU-flash", "GPU-fast", Paths(self.root), self.gpus)
        config = (self.root / "etc/pds4/gpus.conf").read_text()
        self.assertIn("PDS4_FLASH_GPU=GPU-flash", config)
        dropin = self.root / "etc/systemd/system/pds4-flash.service.d/10-gpu-device.conf"
        self.assertIn("/dev/nvidia1", dropin.read_text())

    def test_rejects_same_gpu(self):
        with self.assertRaises(PDS4Error):
            assign("GPU-flash", "GPU-flash", Paths(self.root), self.gpus)

    def test_rejects_wrong_compute_capability(self):
        bad = [self.gpus[0], GPU("GPU-fast", 0, "0000:02:00.0", 20470, "7.5")]
        with self.assertRaises(PDS4Error):
            assign("GPU-flash", "GPU-fast", Paths(self.root), bad)


if __name__ == "__main__":
    unittest.main()
