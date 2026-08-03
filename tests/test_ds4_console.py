import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONSOLE = (ROOT / "scripts" / "ds4-console").read_text(encoding="utf-8")


class UnifiedConsoleTests(unittest.TestCase):
    def test_llama_cli_does_not_use_simple_io(self):
        self.assertNotIn("--simple-io", CONSOLE)

    def test_inference_lock_is_always_released(self):
        acquire = CONSOLE.index('flock -n 9')
        release = CONSOLE.index('flock -u 9')
        close_fd = CONSOLE.index('exec 9>&-')
        self.assertLess(acquire, release)
        self.assertLess(release, close_fd)

    def test_failed_child_keeps_console_available(self):
        self.assertIn('|| rc=$?', CONSOLE)
        self.assertIn('return 0', CONSOLE)


if __name__ == "__main__":
    unittest.main()
