import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location('effort_api', Path(__file__).with_name('api_v2.py'))
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class EffortRoutingTests(unittest.TestCase):
    def test_routine_auto_is_low(self):
        for text in ('Hello', 'Summarize these notes', 'What is 21 times 2?'):
            self.assertEqual(api.resolve_effort('auto', text, {})[0], 'low')

    def test_complex_auto_is_high(self):
        for text in ('Design the architecture', 'Investigate this failure', 'Update the BIOS', 'Review this plan'):
            self.assertEqual(api.resolve_effort('auto', text, {})[0], 'high')
        for profile in ('development', 'network-operations', 'cad', 'finance'):
            self.assertEqual(api.resolve_effort('auto', 'continue', {}, profile)[0], 'high')
        self.assertEqual(api.resolve_effort('auto', 'continue', {'codeGenerationRoute': True})[0], 'high')

    def test_manual_effort_is_preserved(self):
        for level in api.legacy.THINKING - {'auto'}:
            self.assertEqual(api.resolve_effort(level, 'implement it', {'codeGenerationRoute': True})[0], level)

    def test_auto_persists_in_conversation_not_effective_level(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(api, 'META', Path(directory)/'meta.json'):
            api.store_task_route({'sessionId':'session-test', 'thinking':'high', 'requestedThinking':'auto'})
            self.assertEqual(api.metadata()['conversations']['session-test']['thinking'], 'auto')

    def test_catalog_effort_mapping_and_default(self):
        root=Path(__file__).parents[1]/'prime'
        model=json.loads((root/'models.json').read_text())['providers']['spark-qwen']
        self.assertTrue(model['compat']['supportsReasoningEffort'])
        self.assertEqual(model['compat']['thinkingFormat'], 'openai')
        self.assertEqual(model['models'][0]['thinkingLevelMap']['high'], 'xhigh')
        self.assertEqual(model['models'][0]['thinkingLevelMap']['off'], 'none')
        settings=json.loads((root/'settings.json').read_text())
        self.assertEqual(settings['webuiThinkingMode'], 'auto')
        self.assertEqual(settings['defaultThinkingLevel'], 'low')
        self.assertNotIn('spark-nemotron/nemotron-3.5-lightning', settings['enabledModels'])

    def test_auto_setting_never_becomes_native_cli_default(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(api.legacy, 'SETTINGS', Path(directory)/'settings.json'), mock.patch.object(api.legacy, 'model_catalog', return_value=[{'provider':'spark-qwen','model':'qwen3.8-flash-next','configured':True}]):
            result=api.legacy.save_settings({'provider':'spark-qwen','model':'qwen3.8-flash-next','thinking':'auto',
                'reserveTokens':8192,'keepRecentTokens':12000,'enabledProviders':['spark-qwen']})
            self.assertEqual(result['thinking'],'auto')
            self.assertEqual(json.loads(api.legacy.SETTINGS.read_text())['defaultThinkingLevel'],'low')

    def test_opt_in_migration_preserves_unrelated_state_and_backup(self):
        path=Path(__file__).parents[1]/'prime/configure-qwen-only.py'
        spec=importlib.util.spec_from_file_location('qwen_migration',path)
        migration=importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(migration.Path,'home',return_value=Path(directory)), mock.patch('builtins.print'):
            root=Path(directory)/'.prime/agent'; root.mkdir(parents=True)
            old={'defaultProvider':'spark-nemotron','enabledModels':['spark-nemotron/nemotron-3.5-lightning','cloud/model'],'custom':{'keep':True}}
            (root/'settings.json').write_text(json.dumps(old))
            (root/'models.json').write_text(json.dumps({'providers':{'spark-nemotron':{'retained':True},'cloud':{'retained':True}}}))
            migration.main()
            settings=json.loads((root/'settings.json').read_text())
            self.assertEqual(settings['custom'],old['custom'])
            self.assertIn('cloud/model',settings['enabledModels'])
            self.assertEqual(settings['webuiThinkingMode'],'auto')
            self.assertEqual(json.loads(next(root.glob('qwen-only-backup-*/settings.json')).read_text()),old)
            self.assertTrue(json.loads((root/'models.json').read_text())['providers']['spark-nemotron']['retained'])
            self.assertEqual((root/'settings.json').stat().st_mode & 0o777,0o600)


if __name__ == '__main__': unittest.main()
