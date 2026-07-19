import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import os as _os
import unittest
import importlib
import config


class TestConfig(unittest.TestCase):
    def test_data_paths_from_env(self):
        _os.environ["DSCURSO_DATA"] = "/tmp/dscurso-x"
        _os.environ["DSCURSO_ADMIN_TOKEN"] = "segredo123"
        importlib.reload(config)
        self.assertEqual(config.DATA, "/tmp/dscurso-x")
        self.assertTrue(config.drafts_dir().endswith("/drafts"))
        self.assertTrue(config.subscribers_path().endswith("subscribers.json"))
        self.assertEqual(config.ADMIN_TOKEN, "segredo123")
        self.assertEqual(config.SEND_DELAY_SEC, 4.0)


if __name__ == "__main__":
    unittest.main()
