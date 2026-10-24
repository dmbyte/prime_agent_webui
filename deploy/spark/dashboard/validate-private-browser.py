#!/usr/bin/env python3
"""Explicit synthetic LAN HTTPS + actual private broker/worker canary; no real vault.

Start --serve on an unused private-IP TCP 443 (may require sudo), then run --client
as the WebUI host account, preferably under the broker's hardened unit settings.
Stop the fixture server afterward. Never point the client at a real BMC.
"""
import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import ssl
import subprocess
import tempfile
import threading
import time

import connections
from connection_native import NativeRuntime, COMMON
from connection_sessions import Sessions
import skill_credentials

SECRET='synthetic-private-browser-only'


def serve(host):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Synthetic fixture, never a BMC')])
    now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=2))
          .not_valid_after(now-timedelta(days=1)).sign(key,hashes.SHA256()))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def send(self,status,body,cookie=False):
            data=body.encode(); self.send_response(status); self.send_header('Content-Type','text/html')
            self.send_header('Content-Length',str(len(data)))
            if cookie: self.send_header('Set-Cookie','fixture=yes; Secure; HttpOnly; SameSite=Strict')
            self.end_headers(); self.wfile.write(data)
        def do_GET(self):
            if self.path=='/':
                self.send(200,'''<input type=text><input type=password><button onclick="fetch('/login',{method:'POST',body:JSON.stringify({username:document.querySelector('input[type=text]').value,password:document.querySelector('input[type=password]').value})}).then(r=>{if(r.ok)location='/home'})">Log In</button>''')
            elif self.path=='/home' and 'fixture=yes' in self.headers.get('Cookie',''):
                self.send(200,'<h1>Synthetic management status</h1>')
            else: self.send(404,'')
        def do_POST(self):
            length=int(self.headers.get('Content-Length','0'))
            if self.path!='/login' or not 0<length<1000: self.send(400,''); return
            data=json.loads(self.rfile.read(length))
            self.send(200 if data=={'username':'fixture','password':SECRET} else 403,'',True)
    with tempfile.TemporaryDirectory(prefix='prime-private-browser-tls-') as directory:
        root=Path(directory)
        (root/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        (root/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        server=ThreadingHTTPServer((host,443),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(root/'cert.pem',root/'key.pem')
        server.socket=context.wrap_socket(server.socket,server_side=True)
        signal.signal(signal.SIGTERM,lambda *_:threading.Thread(target=server.shutdown).start())
        print('READY: synthetic HTTPS fixture',flush=True)
        try: server.serve_forever()
        finally: server.server_close()


def client(host,state,manifest):
    os.environ['PRIME_CONNECTIONS_ENABLED']='1'
    os.environ['PRIME_CONNECTION_CONSOLES_ENABLED']='1'
    os.environ['PRIME_CONNECTION_CONSOLE_ADAPTERS']='bmc-browser,bmc-kvm'
    home=Path(tempfile.mkdtemp(prefix='synthetic-',dir=state)); config=home/'config'; config.mkdir(mode=0o700)
    agent=home/'.prime/agent'; agent.mkdir(parents=True)
    task='a'*32; owner='fixture'
    declaration={'id':'browser','label':'Synthetic login','adapter':'bmc-browser',
                 'fields':[{'id':k,'label':k} for k in ('endpoint','username','password')]}
    (agent/'webui-metadata.json').write_text(json.dumps({'skills':{'s_fixture':{'owner':owner,'status':'installed','enabled':True,'credentialRequirements':[declaration]}},
        'tasks':{task:{'owner':owner,'status':'running','projectId':None}}}))
    skill_credentials._write(config/'web-auth.json',json.dumps({'users':{owner:{'enabled':True}}}).encode())
    manager=connections.Connections(config,home)
    native=NativeRuntime(home/'leases',manifest); native.reap(startup=True)
    def diagnostic(arguments, **options):
        result=subprocess.run(COMMON+arguments,capture_output=True,**options)
        if result.returncode:
            # This standalone fixture has only synthetic values and no providers.
            print('Fixture CLI failure:',arguments[:2],result.stderr.decode()[:2000],flush=True)
            raise RuntimeError('Fixture OpenShell command failed')
        return result.stdout
    native.run=diagnostic
    manager.sessions=Sessions(manager,native)
    req=manager.requirements(owner)[0]
    values={'endpoint':'https://'+host,'username':'fixture','password':SECRET}
    target=manager.vault.change(owner,[req],{'action':'save-target','name':'Synthetic target','values':values})['key']
    body={'action':'save','name':'Synthetic browser','credentialKey':target,'requirementKey':req['key'],'endpoint':values['endpoint'],
          'projectId':None,'expiresAt':time.time()+600,'enabled':True}
    key=manager.change(owner,body)['id']
    policy={'profile':'network-operations','networkMode':'lan','executionMode':'task','role':'user'}
    token=manager.issue(owner,task,None,policy)
    request={'action':'call','token':token,'connection':key,'operation':'browser.open','arguments':{'requestId':'a'*32}}
    try:
        try: manager.dispatch(request,owner)
        except RuntimeError: pass
        else: raise AssertionError('Strict private browser unexpectedly accepted expired fixture')
        assert not manager.sessions.sessions
        manager.vault.change(owner,[req],{'action':'save-target','key':target,'name':'Synthetic target','values':{},'ignoreCertificateErrors':True})
        manager.change(owner,dict(body,id=key)); manager.revoke(task)
        request['token']=manager.issue(owner,task,None,policy)
        opened=manager.dispatch(request,owner)
        request.update(operation='browser.capture',arguments={'sessionId':opened['sessionId']})
        result=manager.dispatch(request,owner)
        assert result.get('image') and SECRET not in json.dumps(result)
        try: manager.dispatch(request,'another-user')
        except PermissionError: pass
        else: raise AssertionError('Cross-owner private session accepted')
        manager.vault.change(owner,[req],{'action':'save-target','key':target,'name':'Synthetic target','values':{},'ignoreCertificateErrors':False})
        manager.sessions.reap(); assert not manager.sessions.sessions
        assert not list(native.root.glob('pc-*.json'))
        print('PASS: actual private sandbox login/capture, strict denial, saved exception, owner isolation, revocation and cleanup',flush=True)
    finally:
        manager.sessions.reap(all_sessions=True); native.reap(startup=True); manager.revoke(task)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--serve',action='store_true'); mode.add_argument('--client',action='store_true')
    parser.add_argument('--host',required=True); parser.add_argument('--state',type=Path); parser.add_argument('--manifest')
    args=parser.parse_args(); connections.endpoint('https://'+args.host)
    if args.serve: serve(args.host)
    else:
        if not args.state or not args.manifest: parser.error('Client needs private --state and --manifest')
        args.state.mkdir(mode=0o700,parents=True,exist_ok=True); client(args.host,args.state,args.manifest)
