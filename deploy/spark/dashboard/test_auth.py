import base64
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("auth.py")
SPEC = importlib.util.spec_from_file_location("prime_auth", MODULE_PATH)
auth = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auth)


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "web-auth.json"
        salt = b"0123456789abcdef"
        digest = hashlib.scrypt(
            b"correct horse battery staple",
            salt=salt,
            n=auth.SCRYPT_N,
            r=auth.SCRYPT_R,
            p=auth.SCRYPT_P,
            dklen=auth.SCRYPT_BYTES,
            maxmem=auth.SCRYPT_MAXMEM,
        )
        self.path.write_text(json.dumps({
            "version": 1,
            "username": "dbyte",
            "kdf": "scrypt",
            "n": auth.SCRYPT_N,
            "r": auth.SCRYPT_R,
            "p": auth.SCRYPT_P,
            "salt": base64.b64encode(salt).decode(),
            "hash": base64.b64encode(digest).decode(),
        }), encoding="utf-8")
        self.path.chmod(0o600)
        self.environment = patch.dict(os.environ, {"PRIME_AUTH_CREDENTIAL": str(self.path)})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def test_accepts_correct_password(self):
        self.assertTrue(auth.authenticate("dbyte", "correct horse battery staple"))

    def test_rejects_wrong_password_and_user(self):
        self.assertFalse(auth.authenticate("dbyte", "wrong password"))
        self.assertFalse(auth.authenticate("other", "correct horse battery staple"))

    def test_rejects_permissive_or_linked_file(self):
        self.path.chmod(0o640)
        self.assertIsNone(auth.load_credential())
        self.path.unlink()
        self.path.symlink_to(Path(self.temporary.name) / "missing")
        self.assertIsNone(auth.load_credential())


if __name__ == "__main__":
    unittest.main()
