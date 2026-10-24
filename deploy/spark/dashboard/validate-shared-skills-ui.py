#!/usr/bin/env python3
"""Real browser + project API fixture for ordinary-user shared skill selection."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
from http.cookies import SimpleCookie
from playwright.sync_api import sync_playwright

root=Path(__file__).parent
spec=importlib.util.spec_from_file_location('shared_skill_ui',root/'api_v2.py')
api=importlib.util.module_from_spec(spec); spec.loader.exec_module(api)


def main():
    with tempfile.TemporaryDirectory(prefix='prime-shared-skill-ui-') as directory:
        home=Path(directory); agent=home/'.prime/agent'; agent.mkdir(parents=True)
        api.legacy.HOME=home; api.META=agent/'webui-metadata.json'
        project='p_'+'b'*24
        api.save_metadata({'projects':{project:{'owner':'bob','name':'Ordinary user project','skillIds':[]}},'skills':{},'conversations':{}})
        api.credential_declarations._write(agent/'global-skill-inventory.json',json.dumps({'version':1,'scope':'global','generation':'a'*64,
            'skills':[{'id':'managed:bmc-headless-browser','slug':'bmc-headless-browser','name':'Browser fixture','description':'Shared browser helper'}]}).encode())
        (agent/'skill-inventory.json').write_text(json.dumps({'owner':'alice','skills':[
            {'id':'managed:private','slug':'private','name':'Private owner skill'}]}))
        source=(root/'app-v2.js').read_text()
        renderer=source[source.index('function renderInstalledSkills('):source.index('async function loadSkills()')]
        script="let currentProject=null; async function request(url,options={}) {const response=await fetch(url,{...options,headers:{...options.headers,'X-Prime-CSRF':'fixture'}});const data=await response.json(); if(!response.ok)throw Error(data.error); return data;}\n"+renderer+"\nrequest('/api/skills').then(data=>renderInstalledSkills(data,document.getElementById('skills')));"
        class Handler(api.Handler):
            def log_message(self,*_): pass
            def request_user(self):
                cookies=SimpleCookie(); cookies.load(self.headers.get('Cookie',''))
                user=cookies.get('fixture_owner')
                if not user or user.value not in ('alice','bob'): raise ValueError('Fixture identity required')
                return user.value
            def do_GET(self):
                if self.path=='/':
                    raw=('<!doctype html><div id="skills"></div><script>'+script+'</script>').encode()
                    self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers(); self.wfile.write(raw)
                else: super().do_GET()
        server=api.legacy.BoundedThreadingHTTPServer(('127.0.0.1',0),Handler)
        origin=f'http://127.0.0.1:{server.server_port}'; api.legacy.ALLOWED_ORIGINS={origin}
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,**({'executable_path':os.environ['PRIME_TEST_CHROME']} if os.environ.get('PRIME_TEST_CHROME') else {}))
                try:
                    context=browser.new_context()
                    context.add_cookies([{'name':'fixture_owner','value':'bob','url':origin},{'name':'prime_csrf','value':'fixture','url':origin}])
                    page=context.new_page(); page.goto(origin)
                    page.get_by_text('Browser fixture',exact=True).wait_for()
                    assert page.get_by_text('Private owner skill',exact=True).count()==0
                    page.get_by_label('Search installed skills').fill('no match')
                    page.get_by_text('No matching installed skills.',exact=True).wait_for()
                    page.get_by_label('Search installed skills').fill('browser')
                    page.get_by_role('button',name='Add to project',exact=True).click()
                    page.get_by_text('Added to project. Available on its next task.',exact=True).wait_for()
                    assert api.metadata()['projects'][project]['skillIds']==['managed:bmc-headless-browser']
                    page.get_by_role('button',name='Add to project',exact=True).click()
                    assert api.metadata()['projects'][project]['skillIds']==['managed:bmc-headless-browser']
                    context.add_cookies([{'name':'fixture_owner','value':'alice','url':origin}])
                    denied=page.evaluate("async body=>(await fetch('/api/projects/skills',{method:'POST',headers:{'Content-Type':'application/json','X-Prime-CSRF':'fixture'},body:JSON.stringify(body)})).status",{'projectId':project,'skillId':'managed:bmc-headless-browser'})
                    assert denied==400
                    denied=page.evaluate("async body=>(await fetch('/api/projects/skills',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).status",{'projectId':project,'skillId':'managed:bmc-headless-browser'})
                    assert denied==403
                    print('PASS: ordinary-user search/add project, duplicate safety, personal isolation, owner and CSRF denial')
                finally: browser.close()
        finally: server.shutdown(); server.server_close(); thread.join()


if __name__=='__main__': main()
