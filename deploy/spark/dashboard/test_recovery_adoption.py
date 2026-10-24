import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]/'container'))
import runner_launch as runner


class RecoveryAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.agent = Path(self.temp.name); (self.agent/'sessions').mkdir()
        self.sid = 'recovered-'+'a'*32
        self.path = self.agent/'sessions'/f'{self.sid}.jsonl'
        self.body = json.dumps({'type':'session','id':self.sid,'cwd':'/project'})+'\n'
        self.path.write_text(self.body)

    def adopt(self):
        with mock.patch.object(runner.os, 'geteuid', return_value=os.getuid()+1), mock.patch.object(runner.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=os.getuid())):
            runner.adopt_recovered_session(self.agent, self.sid, 'fixture')

    def test_transfer_keeps_original_backup_and_content(self):
        inode = self.path.stat().st_ino
        self.adopt()
        self.assertEqual(self.path.read_text(), self.body)
        self.assertNotEqual(self.path.stat().st_ino, inode)
        backups = list((self.agent/'trash/recovery-ownership-backups').glob('*.jsonl'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), self.body)

    def test_runner_owned_native_transcript_is_untouched(self):
        inode = self.path.stat().st_ino
        runner.adopt_recovered_session(self.agent, self.sid, 'fixture')
        self.assertEqual(self.path.stat().st_ino, inode)
        self.assertFalse((self.agent/'trash').exists())

    def test_symlink_rejected(self):
        target = self.agent/'target'; self.path.rename(target); self.path.symlink_to(target)
        with self.assertRaises(OSError): self.adopt()
        self.assertEqual(target.read_text(), self.body)

    def test_wrong_owner_rejected(self):
        with mock.patch.object(runner.os, 'geteuid', return_value=os.getuid()+1), mock.patch.object(runner.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=os.getuid()+2)):
            with self.assertRaisesRegex(ValueError,'ownership'): runner.adopt_recovered_session(self.agent,self.sid,'fixture')

    def test_header_identity_mismatch_rejected(self):
        self.path.write_text(json.dumps({'type':'session','id':'another-session'}))
        with self.assertRaisesRegex(ValueError,'identity'): self.adopt()

    def test_regular_sessions_never_adopted(self):
        with mock.patch.object(runner.os, 'open') as opened:
            for value in ('ordinary-session', '../unsafe', None):
                runner.adopt_recovered_session(self.agent,value,'fixture')
            opened.assert_not_called()


if __name__ == '__main__': unittest.main()
