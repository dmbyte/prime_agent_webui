#!/usr/bin/env python3
"""Chromium fixture for actual update rendering/click logic; no real upgrades."""
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

source=(Path(sys.argv[1])/'app-v2.js').read_text()
functions='\n'.join(line for line in source.splitlines() if line.startswith((
    'const softwareUpdates=', 'function renderUpdateStatus(', 'function renderReleaseStatus(',
    'async function startSoftwareUpdate(')))
setup='''
const $=id=>document.getElementById(id);
let updateState={},releaseState={},activeUpdates=new Set(),requests=[];
const request=async(url,options)=>{requests.push({url,...options});return {started:true}};
const loadUpdateStatus=async()=>renderUpdateStatus({openshell:{active:true}});
'''
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
                              args=['--disable-dev-shm-usage','--no-zygote'])
    page=browser.new_page()
    page.on('dialog',lambda dialog:dialog.accept())
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.set_content(''.join(f'<section id="{kind}ReleaseBanner"><strong></strong><small></small></section>'
        f'<small id="{kind}UpdateStatus"></small><button id="update{button}">Update</button>'
        for kind,button in [('agent','Agent'),('webui','Webui'),('openshell','Openshell')]))
    page.add_script_tag(content=setup+functions+'\n$("updateOpenshell").onclick=()=>startSoftwareUpdate("openshell");')
    page.evaluate('renderReleaseStatus({openshell:{checkedAt:"now",available:true,installed:"0.1.2",latestName:"OpenShell v0.1.4",blockedReason:"Prime is approved for 0.1.2. Install a compatibility update first."}})')
    assert page.get_by_role('button',name='Requires Prime compatibility update').is_disabled()
    assert 'approved for 0.1.2' in page.locator('#openshellUpdateStatus').inner_text()
    page.evaluate('startSoftwareUpdate("openshell")')
    assert page.evaluate('requests.length')==0
    page.evaluate('renderReleaseStatus({openshell:{checkedAt:"now",available:true,installed:"0.1.2",latestName:"OpenShell v0.1.4"}})')
    page.get_by_role('button',name='Update to OpenShell v0.1.4').click()
    assert page.get_by_role('button',name='Updating…').is_disabled()
    assert page.evaluate('requests[0].url')=='/api/admin/update'
    assert page.evaluate('JSON.parse(requests[0].body).confirm')=='update-openshell'
    page.evaluate('renderUpdateStatus({openshell:{ran:true,result:"failed",reason:"Gateway readiness failed"}})')
    assert page.locator('#openshellUpdateStatus').inner_text()=='Gateway readiness failed'
    page.evaluate('renderUpdateStatus({openshell:{ran:true,result:"success"}});renderReleaseStatus({openshell:{checkedAt:"now",available:false,installed:"0.1.4",latestName:"OpenShell v0.1.4"}})')
    assert page.locator('#updateOpenshell').is_disabled()
    assert page.locator('#updateOpenshell').inner_text()=='Up to date'
    assert 'Installed 0.1.4' in page.locator('#openshellUpdateStatus').inner_text()
    assert not errors,errors
    browser.close()
print('PASS: compatibility blocker, disabled click, confirmed update request, running, failure reason and up-to-date states')
