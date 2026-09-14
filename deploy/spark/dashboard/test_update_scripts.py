#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class UpdateScriptTests(unittest.TestCase):
    def test_webui_update_installs_shared_task_helper(self):
        script = (ROOT / "deploy/spark/update/update-webui.sh").read_text()
        self.assertIn('deploy/spark/container/task_common.py', script)
        self.assertIn('"$live/task_common.py"', script)


if __name__ == "__main__":
    unittest.main()
