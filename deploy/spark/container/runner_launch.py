#!/usr/bin/env python3
"""Validated runner boundary that launches one OpenShell task sandbox."""
import base64, json, os, signal, subprocess, sys, threading, time
import fcntl, pwd, re, stat, tempfile
from pathlib import Path

sys.path.insert(0, "/usr/local/lib/prime-runner")
import openshell_runner
import task_common
import hosting_auth
import volume_provisioner

ROOT=Path("/var/lib/prime-runner")
OPENSHELL_COMMON = ["/usr/bin/openshell", "--gateway", "spark-local"]
def stage(label):
    print(json.dumps({"type": "runtime_stage", "label": label}, separators=(",", ":")), flush=True)
def fake_jwt():
    enc=lambda value: base64.urlsafe_b64encode(json.dumps(value,separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{enc({'alg':'none'})}.{enc({'https://api.openai.com/auth':{'chatgpt_account_id':'gateway'}})}.gateway"

def adopt_recovered_session(agent, session_id, web_owner):
    """Transfer a WebUI recovery transcript by copy, without root or chown.

    Prime preserves ownership during atomic format migration, so an ACL alone
    cannot make a WebUI-owned transcript safely resumable. Keep an exact backup.
    """
    if not session_id or not re.fullmatch(r"recovered-[a-f0-9]{32}", session_id):
        return
    source = agent / "sessions" / f"{session_id}.jsonl"
    lock_fd = os.open(agent / '.recovery-adoption.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if info.st_uid == os.geteuid():
                return
            if not stat.S_ISREG(info.st_mode) or info.st_uid != pwd.getpwnam(web_owner).pw_uid or info.st_size > 2 * 1024 * 1024:
                raise ValueError('Recovered transcript has unsafe ownership, type or size')
            original = stream.read(2 * 1024 * 1024 + 1)
        if len(original) > 2 * 1024 * 1024:
            raise ValueError('Recovered transcript exceeds adoption limit')
        header = json.loads(original.split(b'\n', 1)[0])
        if header.get('type') != 'session' or header.get('id') != session_id:
            raise ValueError('Recovered transcript identity mismatch')
        backups = agent / 'trash' / 'recovery-ownership-backups'
        backups.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup_fd, _ = tempfile.mkstemp(prefix=session_id+'.', suffix='.jsonl', dir=backups)
        with os.fdopen(backup_fd, 'wb') as stream:
            stream.write(original); stream.flush(); os.fsync(stream.fileno())
        target_fd, target_path = tempfile.mkstemp(prefix=session_id+'.', suffix='.tmp', dir=source.parent)
        try:
            with os.fdopen(target_fd, 'wb') as stream:
                os.fchmod(stream.fileno(), 0o660)
                stream.write(original); stream.flush(); os.fsync(stream.fileno())
            current = source.lstat()
            if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns):
                raise ValueError('Recovered transcript changed during adoption')
            os.replace(target_path, source)
        finally:
            Path(target_path).unlink(missing_ok=True)
    finally:
        os.close(lock_fd)


def configure(owner):
    web_owner = os.environ.get("PRIME_WEB_OWNER", "dbyte")
    if not task_common.SAFE_USER.fullmatch(web_owner): raise SystemExit(2)
    workspace_root = Path(os.environ.get("PRIME_RUNNER_WORKSPACE_ROOT", f"/home/{web_owner}/prime-agent/tasks"))
    agent, workspace = task_common.prepare_user_storage(ROOT/"users", owner, workspace_root)
    for relative in ('agent/skills', 'cache/uv', 'cache/pip', 'cache/npm', 'tools/npm', 'tools/playwright'):
        (agent.parent / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
    for source in (ROOT/'kvm'/owner, ROOT/'hosting-access'/owner):
        source.mkdir(mode=0o700, parents=True, exist_ok=True)
    managed = Path('/usr/local/lib/prime-runner/AGENTS.managed.md')
    policy = workspace/'AGENTS.md'
    if managed.is_file() and not policy.exists():
        with policy.open('x') as stream:
            os.chmod(policy, 0o640)
            stream.write(managed.read_text())
    sessions=agent/"sessions"; sessions.mkdir(mode=0o770,exist_ok=True); os.chmod(sessions,0o770)
    trash=agent/"trash"; trash.mkdir(mode=0o770,exist_ok=True); os.chmod(trash,0o770)
    project_sources=agent/"project-sources"; project_sources.mkdir(mode=0o770,exist_ok=True); os.chmod(project_sources,0o770)
    writable_acl = f"u:{web_owner}:rwx,d:u:{web_owner}:rwx,g:prime-web:rwx,d:g:prime-web:rwx,m::rwx,d:m::rwx,o::---,d:o::---"
    traverse_acl = f"u:{web_owner}:--x,g:prime-web:--x,m::--x"
    for path, permissions in ((agent.parents[1], traverse_acl), (agent.parent, traverse_acl), (agent, traverse_acl), (sessions, writable_acl), (trash, writable_acl), (project_sources, writable_acl), (agent/'skills', writable_acl)):
        subprocess.run(["/usr/bin/setfacl", "-m", permissions, str(path)], check=True)
    # The OpenShell gateway runs as the installer/WebUI owner and validates
    # bind sources before asking Docker to mount them. Directory read/traverse
    # is required for that validation; files and sockets retain their own
    # prime-runner-only permissions.
    subprocess.run(["/usr/bin/setfacl", "-m", f"u:{web_owner}:rx,m::rx", str(agent)], check=True)
    subprocess.run(["/usr/bin/setfacl", "-m", writable_acl, str(workspace)], check=True)
    gateway = ROOT/"gateway"
    for path in (gateway, gateway/owner):
        if path.exists():
            subprocess.run(["/usr/bin/setfacl", "-m", f"u:{web_owner}:rx,m::rx", str(path)], check=True)
    for mode in ("restricted", "internet", "lan", "full"):
        path = gateway/owner/mode
        if path.exists():
            subprocess.run(["/usr/bin/setfacl", "-m", f"u:{web_owner}:--x,m::--x", str(path)], check=True)
    models={"providers":{
      "spark-nemotron":{"baseUrl":"http://127.0.0.1:31000/spark-nemotron/v1","api":"openai-completions","apiKey":"gateway","compat":{"supportsDeveloperRole":False,"supportsReasoningEffort":False},"models":[{"id":"nemotron-3.5-lightning","name":"Nemotron 3.5 Lightning + DSpark","reasoning":True,"contextWindow":262144,"maxTokens":8192}]},
      "spark-qwen":{"baseUrl":"http://127.0.0.1:31000/spark-qwen/v1","api":"openai-completions","apiKey":"gateway","compat":{"supportsDeveloperRole":False,"supportsReasoningEffort":True,"thinkingFormat":"openai"},"models":[{"id":"qwen3.8-flash-next","name":"Qwen 3.8 Flash Next UD-IQ4_XS","reasoning":True,"input":["text","image"],"contextWindow":262144,"maxTokens":8192,"thinkingLevelMap":{"off":"none","minimal":"low","low":"low","medium":"medium","high":"xhigh","xhigh":"xhigh","max":"xhigh"}}]},
      "openai-codex":{"baseUrl":"http://127.0.0.1:31000/openai-codex","apiKey":"gateway"}}}
    for name,value in (("models.json",models),("auth.json",{"openai-codex":{"type":"oauth","access":fake_jwt(),"refresh":"gateway","expires":4102444800000,"accountId":"gateway"}})):
        path=agent/name; temporary=agent/(name+".tmp"); temporary.write_text(json.dumps(value)); os.chmod(temporary,0o600); os.replace(temporary,path)

def forward_stdin_to_fifo(sandbox, fifo_path):
    writer = [
        *OPENSHELL_COMMON, "sandbox", "exec", "--name", sandbox, "--no-tty", "--",
        "/usr/bin/python3", "-c",
        "import base64,pathlib,sys; pathlib.Path(sys.argv[1]).open('ab', buffering=0).write(base64.b64decode(sys.argv[2]))",
        fifo_path,
    ]
    while True:
        # Use the unbuffered file descriptor. A daemon thread blocked in
        # BufferedReader.readline() can hold stdin's internal lock while the
        # interpreter finalizes after Prime exits, causing a fatal SIGABRT and
        # a false "task broker exited" result for an otherwise completed task.
        chunk = os.read(sys.stdin.fileno(), 65536)
        if not chunk:
            return
        payload = base64.b64encode(chunk).decode()
        subprocess.run([*writer, payload], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)

def prepare_connection_capability(spec, token):
    """Send a task-only capability via stdin, never CLI argv or model prompts."""
    path = spec['inputFifo'] + '.connection'
    writer = ('import os,sys; data=sys.stdin.buffer.read(101); '
              'assert len(data)==97; '
              'fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); '
              'os.write(fd,data); os.close(fd)')
    command = [*OPENSHELL_COMMON, 'sandbox', 'exec', '--name', spec['name'], '--no-tty',
               '--no-login-shell', '--', '/usr/bin/python3', '-c', writer, path]
    subprocess.run(command, input=token.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=30, check=True)
    marker = spec['execute'].index('--', spec['execute'].index('exec'))
    script_at = marker + 3  # -- /usr/bin/python3 -c <relay>
    if spec['execute'][marker+1:script_at] != ['/usr/bin/python3', '-c']:
        raise ValueError('Unexpected sandbox relay command')
    load = (f'import os; fd=os.open({path!r},os.O_RDONLY|os.O_NOFOLLOW); '
            'os.environ["PRIME_CONNECTION_TOKEN"]=os.read(fd,101).decode(); '
            f'os.close(fd); os.unlink({path!r}); ')
    spec['execute'][script_at] = load + spec['execute'][script_at]


def main():
    if len(sys.argv)!=2 or len(sys.argv[1])>32768: raise SystemExit(2)
    request=json.loads(base64.urlsafe_b64decode(sys.argv[1]+"=="))
    allowed={"taskId","owner","authorization","provider","model","thinking","sessionId","fork"}
    if set(request) not in (allowed, allowed | {'projectId'}): raise SystemExit(2)
    connection_token = os.environ.pop('PRIME_CONNECTION_TOKEN', None)
    if connection_token and (not isinstance(connection_token, str) or not re.fullmatch(re.escape(request['taskId']) + r'\.[a-f0-9]{64}', connection_token)):
        raise SystemExit(2)
    stage("Preparing task storage")
    configure(request["owner"])
    child = None
    sandbox = None
    policy_path = None
    hosting_token = None
    stop_requested = False
    def stop_child(_signum, _frame):
        nonlocal stop_requested
        stop_requested = True
        if child and child.poll() is None:
            try: os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError: pass
    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)
    try:
        stage("Checking model gateway")
        gateway=ROOT/"gateway"/request["owner"]/request["authorization"].get("networkMode","restricted")/"model.sock"
        for _ in range(30):
            if gateway.is_socket(): break
            time.sleep(0.1)
        else: raise SystemExit("Task gateway is unavailable")
        stage("Registering user OpenShell storage")
        volume_provisioner.provision(request['owner'])
        if request.get('sessionId'):
            adopt_recovered_session(ROOT/'users'/request['owner']/'prime/agent',
                                    request['sessionId'], os.environ.get('PRIME_WEB_OWNER', 'dbyte'))
        os.environ["HOME"] = str(ROOT)
        os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        # Path validation and argv construction can fail before OpenShell starts.
        # Keep them inside the restoration boundary so a rejected local path
        # cannot leave the WebUI unable to traverse its conversation storage.
        stage("Preparing OpenShell policy")
        spec=openshell_runner.task_spec(request["taskId"],request["owner"],request["authorization"],request["provider"],request["model"],request["thinking"],request["sessionId"],request["fork"],ROOT/"users",ROOT/"openshell-image-digests.json",ROOT/"openshell-policies",Path(os.environ.get("PRIME_RUNNER_WORKSPACE_ROOT", f"/home/{os.environ.get('PRIME_WEB_OWNER', 'dbyte')}/prime-agent/tasks")))
        hosting_token = hosting_auth.issue(request['owner'], request['taskId'], request.get('projectId'), request['authorization'], ROOT)
        if hosting_token:
            marker = spec['execute'].index('--', spec['execute'].index('exec'))
            spec['execute'][marker:marker] = ['--env', 'PRIME_HOSTING_TOKEN=' + hosting_token,
                                             '--env', 'PRIME_PROJECT_ID=' + (request.get('projectId') or '')]
        sandbox, policy_path = spec["name"], spec["policy"]
        stage("Creating OpenShell sandbox")
        child = subprocess.Popen(spec["create"], stdin=subprocess.DEVNULL, start_new_session=True)
        if child.wait() != 0:
            raise SystemExit("OpenShell could not create the task sandbox")
        subprocess.run(spec["prepareInput"], stdin=subprocess.DEVNULL, check=True)
        if connection_token:
            prepare_connection_capability(spec, connection_token)
        stage("Launching Prime inside sandbox")
        child = subprocess.Popen(spec["execute"], stdin=subprocess.DEVNULL, start_new_session=True)
        threading.Thread(target=forward_stdin_to_fifo, args=(sandbox, spec["inputFifo"]), daemon=True).start()
        if stop_requested and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
        returncode = child.wait()
    finally:
        if hosting_token:
            hosting_auth.revoke(request['taskId'], ROOT)
        if sandbox:
            subprocess.run(["/usr/bin/openshell", "--gateway", "spark-local", "sandbox", "delete", sandbox], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
        if policy_path:
            try: policy_path.unlink()
            except FileNotFoundError: pass
        # Prime protects its state with chmod(0700) while it runs. Restore the
        # API's named ACL only after the isolated task has released the tree.
        configure(request["owner"])
    raise SystemExit(returncode)
if __name__=="__main__": main()
