"""Offline tests for owner-log credential migration."""

import tempfile
import unittest
from pathlib import Path

import scrub_task_logs as scrub


class LogScrubberTests(unittest.TestCase):
    def test_removes_literal_and_preserves_other_log_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / ("a" * 32 + ".log")
            second = root / ("b" * 32 + ".log")
            seed.write_text('{"type":"message_end","message":{"content":[{"type":"toolCall","arguments":{"code":"request(auth=(\\"operator\\", \\"synthetic-private-value\\"))"}}]}}\n')
            second.write_text('ordinary result synthetic-private-value\n')
            seed.chmod(0o600)
            second.chmod(0o600)
            secrets = scrub.auth_literals(seed)
            self.assertEqual(secrets, {"synthetic-private-value"})
            self.assertTrue(scrub.scrub_file(seed, secrets))
            self.assertTrue(scrub.scrub_file(second, secrets))
            self.assertNotIn("synthetic-private-value", seed.read_text() + second.read_text())
            self.assertIn("ordinary result", second.read_text())
            self.assertFalse(scrub.scrub_file(second, secrets))


if __name__ == "__main__":
    unittest.main()
