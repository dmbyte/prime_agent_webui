#!/usr/bin/env python3
import importlib.util
import io
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("prime_dashboard_api", Path(__file__).with_name("api.py"))
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)


class DashboardSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.original_uploads = api.UPLOADS
        self.original_limit = api.MAX_UPLOAD_STORAGE_BYTES
        self.original_sessions = api.SESSIONS
        self.original_trash = api.SESSION_TRASH
        api.UPLOADS = Path(self.temporary.name) / "uploads"
        api.SESSIONS = Path(self.temporary.name) / "sessions"
        api.SESSION_TRASH = Path(self.temporary.name) / "trash"
        api.MAX_UPLOAD_STORAGE_BYTES = 32

    def tearDown(self):
        api.UPLOADS = self.original_uploads
        api.SESSIONS = self.original_sessions
        api.SESSION_TRASH = self.original_trash
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

    def test_idle_live_conversation_is_not_treated_as_running(self):
        payload = b'prefix {"sessions":[{"id":"idle-session","lifecycle":"live","activity":"idle","isSessionActive":false,"attachedClients":0,"unfinishedActionCount":0,"sessionActions":{"queuedCount":0}}]}'
        with mock.patch.object(api.subprocess, "run", return_value=mock.Mock(stdout=payload.decode())):
            self.assertEqual(api.live_session_ids(), set())

    def test_actual_conversation_activity_blocks_deletion(self):
        payload = b'prefix {"sessions":[{"id":"busy-session","lifecycle":"live","activity":"idle","isSessionActive":true,"attachedClients":0,"unfinishedActionCount":0,"sessionActions":{"queuedCount":0}}]}'
        with mock.patch.object(api.subprocess, "run", return_value=mock.Mock(stdout=payload.decode())):
            self.assertEqual(api.live_session_ids(), {"busy-session"})

    def test_idle_conversation_moves_to_recovery_storage(self):
        session_id = "idle-session-1234"
        api.SESSIONS.mkdir()
        source = api.SESSIONS / f"{session_id}.jsonl"
        source.write_text('{"type":"session"}\n')
        with mock.patch.object(api, "live_session_ids", return_value=set()):
            result = api.delete_conversation(session_id)
        self.assertFalse(source.exists())
        self.assertEqual(len(list(api.SESSION_TRASH.glob(f"{session_id}.*.jsonl"))), 1)
        self.assertTrue(result["recoverable"])

    def test_internal_id_resolves_different_storage_filename(self):
        storage_id = "storage-session-1234"
        internal_id = "internal-session-5678"
        api.SESSIONS.mkdir()
        source = api.SESSIONS / f"{storage_id}.jsonl"
        source.write_text(f'{{"type":"session","id":"{internal_id}"}}\n')
        self.assertEqual(api.session_path(internal_id), source)
        with mock.patch.object(api, "live_session_ids", return_value=set()):
            result = api.delete_conversation(internal_id)
        self.assertEqual(result["storageId"], storage_id)
        self.assertEqual(len(list(api.SESSION_TRASH.glob(f"{storage_id}.*.jsonl"))), 1)

    def test_active_storage_alias_is_protected(self):
        payload = b'prefix {"sessions":[{"id":"internal-session","sessionFile":"/tmp/storage-session.jsonl","activity":"working"}]}'
        with mock.patch.object(api.subprocess, "run", return_value=mock.Mock(stdout=payload.decode())):
            self.assertEqual(api.live_session_ids(), {"internal-session", "storage-session"})


if __name__ == "__main__":
    unittest.main()
