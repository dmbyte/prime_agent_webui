#!/usr/bin/env python3
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("prime_dashboard_api", Path(__file__).with_name("api.py"))
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)


class DashboardSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.original_uploads = api.UPLOADS
        self.original_limit = api.MAX_UPLOAD_STORAGE_BYTES
        api.UPLOADS = Path(self.temporary.name) / "uploads"
        api.MAX_UPLOAD_STORAGE_BYTES = 32

    def tearDown(self):
        api.UPLOADS = self.original_uploads
        api.MAX_UPLOAD_STORAGE_BYTES = self.original_limit
        self.temporary.cleanup()

    def test_filename_cannot_escape_upload_root(self):
        self.assertEqual(api.safe_upload_name("..%2F..%2Fsecret.txt"), "secret.txt")

    def test_long_unicode_filename_fits_filesystem_limit(self):
        result = api.safe_upload_name(("é" * 200) + ".txt")
        self.assertLessEqual(len(result.encode("utf-8")), 180)
        self.assertTrue(result.endswith(".txt"))

    def test_upload_is_private_and_hashed(self):
        payload = b"private upload"
        result = api.save_upload(io.BytesIO(payload), len(payload), "report.txt")
        path = Path(result["path"])
        self.assertEqual(path.read_bytes(), payload)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(result["sha256"], "4f9f2b8a6dcf448cabbdfdc6901dbe7db004b27bceec6bf26dc128381a86b1ca")

    def test_aggregate_quota_is_enforced(self):
        api.save_upload(io.BytesIO(b"a" * 20), 20, "one.bin")
        with self.assertRaisesRegex(ValueError, "2 GiB limit"):
            api.save_upload(io.BytesIO(b"b" * 20), 20, "two.bin")


if __name__ == "__main__":
    unittest.main()
