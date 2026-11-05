#!/usr/bin/env python3
"""Isolated real-browser recovery card + real HTTP authentication acceptance.

Uses synthetic accounts and temporary metadata. No production auth, model,
credentials, BMC or task runner is contacted. Requires playwright/cryptography.
"""
import json
import os
from pathlib import Path
from unittest import mock

from playwright.sync_api import sync_playwright
from test_reliable_core import CheckpointTests, IdentityBoundaryTests, api, auth


def main():
    records = CheckpointTests(); records.setUp()
    boundary = IdentityBoundaryTests(); boundary.setUp()
    try:
        api.apply_task_event(records.tid, {'type':'tool_execution_start', 'toolName':'ipython', 'toolCallId':'fixture-step'})
        api.TASKS.clear(); api.restore_task_checkpoints()
        auth.SESSIONS['bob-session'] = dict(auth.SESSIONS['alice-session'], user='bob', csrf='bob-csrf')
        source = (Path(__file__).parent/'app-v2.js').read_text()
        renderer = source[source.index('function renderTaskOutcome('):source.index('function syncWorkLogCards(')]
        script = renderer + """
async function load(){
 const response=await fetch('/api/tasks');
 const data=await response.json();
 document.querySelector('#status').textContent=String(response.status);
 for(const task of data.tasks||[]){
  const card=document.createElement('article');card.innerHTML='<details><summary>Work log</summary></details>';
  renderTaskOutcome(card,task);document.querySelector('main').append(card);
 }
}load();
"""
        original = api.Handler.do_GET
        def serve(handler):
            if handler.path != '/': return original(handler)
            body = ('<!doctype html><title>Recovery acceptance</title><p id="status"></p><main></main><script>'+script+'</script>').encode()
            handler.send_response(200); handler.send_header('Content-Type','text/html'); handler.end_headers(); handler.wfile.write(body)
        with mock.patch.object(api.Handler, 'do_GET', serve), sync_playwright() as p:
            browser = p.chromium.launch(headless=True, **({'executable_path':os.environ['PRIME_TEST_CHROME']} if os.environ.get('PRIME_TEST_CHROME') else {}))
            try:
                origin = f'http://127.0.0.1:{boundary.server.server_port}'
                context = browser.new_context()
                context.add_cookies([{'name':'prime_session','value':'alice-session','url':origin}])
                page = context.new_page(); page.goto(origin)
                page.locator('#status').get_by_text('200', exact=True).wait_for()
                page.locator('.runtime-report').wait_for(state='visible')
                assert 'unverified' in page.locator('.runtime-report').inner_text()
                assert not page.locator('details').evaluate('(node)=>node.open')
                page.get_by_text('Work log', exact=True).click()
                page.get_by_text('ipython: unknown', exact=True).wait_for(state='visible')
                page.reload(); page.locator('.runtime-report').wait_for(state='visible')
                context.add_cookies([{'name':'prime_session','value':'bob-session','url':origin}])
                page.reload(); page.locator('#status').get_by_text('200', exact=True).wait_for()
                assert page.locator('.runtime-report').count()==0, 'Cross-user checkpoint leak'
                context.clear_cookies(); page.reload()
                page.locator('#status').get_by_text('401', exact=True).wait_for()
                assert page.locator('.runtime-report').count()==0
                print('PASS: visible final status, collapsed steps, unknown outcome, reload persistence, owner isolation, login required')
            finally: browser.close()
    finally:
        boundary.doCleanups(); records.doCleanups()


if __name__ == '__main__': main()
