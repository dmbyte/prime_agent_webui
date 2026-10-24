import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('shared_skills', Path(__file__).parents[1]/'container/shared_skills.py')
shared = importlib.util.module_from_spec(spec); spec.loader.exec_module(shared)
spec = importlib.util.spec_from_file_location('shared_installer', Path(__file__).parents[1]/'prime/install-managed-skills.py')
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)


class SharedSkillTests(unittest.TestCase):
    def test_reviewed_publication_and_new_user_provision_preserve_personal_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); home=root/'web'; (home/'.prime/agent').mkdir(parents=True)
            bundled=Path(__file__).parents[1]/'prime/skills'
            registry=root/'registry'
            account=mock.Mock(pw_dir=str(home),pw_uid=os.geteuid(),pw_gid=os.getegid())
            with mock.patch.object(installer.pwd,'getpwnam',return_value=account):
                installer.publish_shared('admin',bundled,root=registry)
            index=json.loads((home/'.prime/agent/global-skill-inventory.json').read_text())
            self.assertEqual(len(index['skills']),5)
            for owner in ('alice','bob'):
                agent=root/owner; (agent/'skills/bmc-headless-browser').mkdir(parents=True)
                (agent/'skills/bmc-headless-browser/SKILL.md').write_text('personal')
                shared.provision(agent,registry,os.geteuid())
                shared.provision(agent,registry,os.geteuid())
                self.assertEqual((agent/'skills/bmc-headless-browser/SKILL.md').read_text(),'personal')
                self.assertTrue((agent/'skills/bmc-html5-kvm/SKILL.md').is_file())
                global_path=agent/'shared-skills'/index['generation']/'skills/bmc-headless-browser/SKILL.md'
                self.assertIn('bmc-headless-browser',global_path.read_text())
            self.assertNotEqual((root/'alice/skills/bmc-html5-kvm').resolve(),(root/'bob/skills/bmc-html5-kvm').resolve())

    def test_provision_rejects_user_symlink_and_unsafe_global_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); registry=root/'registry'; registry.mkdir()
            generation='a'*64; (registry/generation/'skills').mkdir(parents=True)
            manifest=registry/'current.json'; manifest.write_text(json.dumps({'generation':generation})); manifest.chmod(0o644)
            agent=root/'agent'; agent.mkdir(); outside=root/'outside'; outside.mkdir()
            (agent/'shared-skills').symlink_to(outside)
            with self.assertRaises(ValueError): shared.provision(agent,registry,os.geteuid())
            self.assertFalse(list(outside.iterdir()))
            manifest.chmod(0o666)
            with self.assertRaises(ValueError): shared.provision(agent,registry,os.geteuid())

    def test_shared_nvidia_rejects_dirty_or_unpinned_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with mock.patch.object(installer.subprocess,'check_output',side_effect=[installer.NVIDIA_COMMIT,' M skills/changed']):
                with self.assertRaises(ValueError):
                    installer.publish_shared('admin',Path(__file__).parents[1]/'prime/skills',root,root/'registry')
