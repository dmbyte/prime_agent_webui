import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('update_api', Path(__file__).with_name('api_v2.py'))
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class OpenShellUpdateTests(unittest.TestCase):
    def test_reviewed_pin_controls_upgrade_not_upstream_availability(self):
        with tempfile.TemporaryDirectory() as directory:
            installer = Path(directory)/'deploy/spark/openshell/install.sh'
            installer.parent.mkdir(parents=True)
            installer.write_text('version=0.1.4\n')
            with mock.patch.dict(api.os.environ, {'PRIME_WEBUI_REPO':directory}):
                self.assertIsNone(api.openshell_upgrade_blocker('0.1.2','v0.1.4'))
                self.assertIn('approved for 0.1.4', api.openshell_upgrade_blocker('0.1.4','v0.1.5'))
                self.assertIn('migration', api.openshell_upgrade_blocker('0.0.116','v0.1.4'))
                self.assertIsNone(api.openshell_upgrade_blocker('0.1.4','v0.1.4'))
                self.assertIn('Cannot verify', api.openshell_upgrade_blocker('unknown','v0.1.4'))
                installer.unlink()
                self.assertIn('unknown version', api.openshell_upgrade_blocker('0.1.2','v0.1.4'))

    def test_preflight_refuses_unapproved_release(self):
        results = [mock.Mock(stdout='openshell 0.1.2'), mock.Mock(stdout='{"tag_name":"v0.1.5"}')]
        with mock.patch.object(api.subprocess, 'run', side_effect=results), mock.patch.object(api, 'openshell_upgrade_blocker', return_value='Review required'):
            with self.assertRaisesRegex(RuntimeError,'Review required'):
                api.openshell_update_preflight()

    def test_start_does_not_start_service_when_preflight_blocks(self):
        with mock.patch.object(api,'update_status',return_value={}), mock.patch.object(api.subprocess,'run',return_value=mock.Mock(stdout='')) as command, mock.patch.object(api,'openshell_update_preflight',side_effect=RuntimeError('Review required')):
            with self.assertRaisesRegex(RuntimeError,'Review required'):
                api.start_update('openshell','update-openshell')
            self.assertEqual(command.call_count,1)
            self.assertNotIn('systemctl', command.call_args.args[0])

    def test_release_response_exposes_blocker(self):
        def run(args, **kwargs):
            if args[0]=='openshell':
                return mock.Mock(stdout='openshell 0.1.2')
            if args[:2]==['gh','api']:
                return mock.Mock(stdout=json.dumps({'tag_name':'v0.1.4','html_url':'https://github.com/NVIDIA/OpenShell/releases/tag/v0.1.4'}))
            return mock.Mock(stdout='invalid')
        with mock.patch.object(api.subprocess,'run',side_effect=run), mock.patch.object(api,'openshell_upgrade_blocker',return_value='Review required'):
            row=api.release_status()['openshell']
        self.assertTrue(row['available'])
        self.assertFalse(row['updateAllowed'])
        self.assertEqual(row['blockedReason'],'Review required')

    def test_ui_distinguishes_blocked_available_running_and_failed(self):
        source=Path(__file__).with_name('app-v2.js').read_text()
        functions='\n'.join(line for line in source.splitlines() if line.startswith(('function renderUpdateStatus(', 'function renderReleaseStatus(', 'async function startSoftwareUpdate(')))
        script='''const assert=require('node:assert/strict');
let updateState={},releaseState={},activeUpdates=new Set();
const nodes={},$=id=>nodes[id]||(nodes[id]={querySelector(sel){return $(id+sel)},classList:{toggle(){}}});
const softwareUpdates={openshell:{status:'status',button:'button',banner:'banner',label:'OpenShell'}};
let requested=0;const request=async()=>{requested++},confirm=()=>true,alert=()=>{},loadUpdateStatus=async()=>{};
'''+functions+'''
(async()=>{
renderReleaseStatus({openshell:{checkedAt:'now',available:true,installed:'0.1.2',latestName:'0.1.4',blockedReason:'Review required'}});
assert.equal($('button').disabled,true);assert.match($('button').textContent,/compatibility/);
assert.equal($('status').textContent,'Review required');assert.match($('bannerstrong').textContent,/review required/);
await startSoftwareUpdate('openshell');assert.equal(requested,0);
renderReleaseStatus({openshell:{checkedAt:'now',available:true,latestName:'0.1.4'}});
assert.equal($('button').disabled,false);assert.match($('button').textContent,/Update to/);
await startSoftwareUpdate('openshell');assert.equal(requested,1);
renderUpdateStatus({openshell:{active:true}});assert.equal($('button').textContent,'Updating…');
renderUpdateStatus({openshell:{ran:true,result:'failed',reason:'Configuration rejected'}});
assert.equal($('status').textContent,'Configuration rejected');
renderReleaseStatus({openshell:{checkedAt:'now',available:false,installed:'0.1.4',latestName:'0.1.4'}});
assert.equal($('button').disabled,true);assert.equal($('button').textContent,'Up to date');
})().catch(error=>{console.error(error);process.exit(1)});
'''
        subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)

    def test_script_checks_pin_hash_configuration_and_sandboxes_before_install(self):
        source=(Path(__file__).parents[1]/'update/update-openshell.sh').read_text()
        install=source.index('sudo -n apt-get install')
        self.assertLess(source.index('"$pinned_sha" "$asset"'),install)
        self.assertLess(source.index('config preflight'),install)
        self.assertEqual(source.count('sandbox_ids=$(openshell'),2)
        self.assertIn('failure_reason="OpenShell update failed while ${phase}',source)

    def test_gateway_readiness_is_retried_even_when_package_is_current(self):
        source=(Path(__file__).parents[1]/'update/update-openshell.sh').read_text()
        self.assertIn('for attempt in {1..30}',source)
        self.assertIn('timeout 5s sudo -n -u prime-runner',source)
        current=source.split('if ! dpkg --compare-versions "$version" gt "$installed"; then',1)[1].split('fi',1)[0]
        self.assertLess(current.index('verify_gateway'),current.index('set_dashboard_version'))
        self.assertIn('systemctl --user restart openshell-gateway.service\nverify_gateway',source)

    def test_readiness_function_retries_and_fails_boundedly(self):
        source=(Path(__file__).parents[1]/'update/update-openshell.sh').read_text()
        function='verify_gateway() {'+source.split('verify_gateway() {',1)[1].split('\n}\n',1)[0]+'\n}\n'
        setup='calls=0; waits=0; phase=""; failure_reason=""; sleep(){ ((waits+=1)); }; openshell(){ return 0; };\n'
        success=setup+'timeout(){ ((calls+=1)); (( calls > 1 )); };\n'+function+'verify_gateway && test "$calls" = 3 && test "$waits" = 1'
        subprocess.run(['bash','-c',success],check=True,capture_output=True,text=True)
        failed=setup+'timeout(){ ((calls+=1)); return 1; };\n'+function+'! verify_gateway && test "$calls" = 30 && test "$waits" = 30 && test -n "$failure_reason"'
        subprocess.run(['bash','-c',failed],check=True,capture_output=True,text=True)
