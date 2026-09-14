#!/usr/bin/env python3
import unittest
from pathlib import Path


class RunnerBrokerRegressionTests(unittest.TestCase):
    def test_client_disconnect_returns_to_launcher_cleanup(self):
        source = (Path(__file__).parents[1] / "container" / "runner_broker.py").read_text()
        disconnect_at = source.index("process.stdin.close(); selector.unregister(conn)")
        return_at = source.index("return", disconnect_at)
        finally_at = source.index("finally:")
        terminate_at = source.index("process.terminate()", finally_at)
        self.assertLess(disconnect_at, return_at)
        self.assertLess(return_at, finally_at)
        self.assertLess(finally_at, terminate_at)


if __name__ == "__main__":
    unittest.main()
