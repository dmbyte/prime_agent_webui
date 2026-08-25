#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("prime_dashboard_api_v2", Path(__file__).with_name("api_v2.py"))
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)


class DashboardV2Tests(unittest.TestCase):
    def test_archive_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../../escape.txt", "no")
            with self.assertRaisesRegex(ValueError, "unsafe path"):
                api.inspect_archive(path)

    def test_archive_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "link.zip"
            info = zipfile.ZipInfo("link")
            info.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(info, "target")
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                api.inspect_archive(path)

    def test_upload_identifier_cannot_escape_root(self):
        original = api.legacy.UPLOADS
        with tempfile.TemporaryDirectory() as directory:
            api.legacy.UPLOADS = Path(directory) / "uploads"
            api.legacy.UPLOADS.mkdir()
            encoded = "Li4vb3V0c2lkZQ"
            with self.assertRaisesRegex(ValueError, "File not found"):
                api.upload_path(encoded)
        api.legacy.UPLOADS = original


if __name__ == "__main__":
    unittest.main()
