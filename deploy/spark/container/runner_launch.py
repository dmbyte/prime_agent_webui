#!/usr/bin/env python3
"""Validated runner boundary that launches one OpenShell task sandbox."""
import base64, json, os, signal, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, "/usr/local/lib/prime-runner")
import openshell_runner
import task_common

ROOT=Path("/var/lib/prime-runner")
def fake_jwt():
    enc=lambda value: base64.urlsafe_b64encode(json.dumps(value,separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{enc({'alg':'none'})}.{enc({'https://api.openai.com/auth':{'chatgpt_account_id':'gateway'}})}.gateway"

def configure(owner):
    web_owner = os.environ.get("PRIME_WEB_OWNER", "dbyte")
    if not task_common.SAFE_USER.fullmatch(web_owner): raise SystemExit(2)
    agent, workspace = task_common.prepare_user_storage(ROOT/"users", owner)
    sessions=agent/"sessions"; sessions.mkdir(mode=0o770,exist_ok=True); os.chmod(sessions,0o770)
    trash=agent/"trash"; trash.mkdir(mode=0o770,exist_ok=True); os.chmod(trash,0o770)
    project_sources=agent/"project-sources"; project_sources.mkdir(mode=0o770,exist_ok=True); os.chmod(project_sources,0o770)
    writable_acl = f"u:{web_owner}:rwx,d:u:{web_owner}:rwx,g:prime-web:rwx,d:g:prime-web:rwx,m::rwx,d:m::rwx,o::---,d:o::---"
    traverse_acl = f"u:{web_owner}:--x,g:prime-web:--x,m::--x"
    for path, permissions in ((agent.parents[1], traverse_acl), (agent.parent, traverse_acl), (agent, traverse_acl), (sessions, writable_acl), (trash, writable_acl), (project_sources, writable_acl)):
        subprocess.run(["/usr/bin/setfacl", "-m", permissions, str(path)], check=True)
    # The OpenShell gateway runs as the installer/WebUI owner and validates
    # bind sources before asking Docker to mount them. Directory read/traverse
    # is required for that validation; files and sockets retain their own
    # prime-runner-only permissions.
    for path in (agent, workspace):
        subprocess.run(["/usr/bin/setfacl", "-m", f"u:{web_owner}:rx,m::rx", str(path)], check=True)
    gateway = ROOT/"gateway"
    for path in (gateway, gateway/owner):
        if path.exists():
            subprocess.run(["/usr/bin/setfacl", "-m", f"u:{web_owner}:rx,m::rx", str(path)], check=True)
    for mode in ("restricted", "internet", "lan", "full"):
        path = gateway/owner/mode
        if path.exists():
            subprocess.run(["/usr/bin/setfacl", "-m", f"u:{web_owner}:--x,m::--x", str(path)], check=True)
    models={"providers":{
      "spark-nemotron":{"baseUrl":"http://127.0.0.1:31000/spark-nemotron/v1","api":"openai-completions","apiKey":"gateway","compat":{"supportsDeveloperRole":False,"supportsReasoningEffort":False},"models":[{"id":"nemotron-3.5-lightning","name":"Nemotron 3.5 Lightning + DSpark","reasoning":True,"contextWindow":81920,"maxTokens":8192}]},
      "spark-qwen":{"baseUrl":"http://127.0.0.1:31000/spark-qwen/v1","api":"openai-completions","apiKey":"gateway","compat":{"supportsDeveloperRole":False,"supportsReasoningEffort":False},"models":[{"id":"qwen3.8-flash-next","name":"Qwen 3.8 Flash Next UD-IQ4_XS","reasoning":True,"input":["text","image"],"contextWindow":32768,"maxTokens":8192}]},
      "openai-codex":{"baseUrl":"http://127.0.0.1:31000/openai-codex","apiKey":"gateway"}}}
    for name,value in (("models.json",models),("auth.json",{"openai-codex":{"type":"oauth","access":fake_jwt(),"refresh":"gateway","expires":4102444800000,"accountId":"gateway"}})):
        path=agent/name; temporary=agent/(name+".tmp"); temporary.write_text(json.dumps(value)); os.chmod(temporary,0o600); os.replace(temporary,path)

def main():
    if len(sys.argv)!=2 or len(sys.argv[1])>32768: raise SystemExit(2)
    request=json.loads(base64.urlsafe_b64decode(sys.argv[1]+"=="))
    allowed={"taskId","owner","authorization","provider","model","thinking","sessionId","fork"}
    if set(request)!=allowed: raise SystemExit(2)
    configure(request["owner"])
    child = None
    sandbox = None
    policy_path = None
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
        gateway=ROOT/"gateway"/request["owner"]/request["authorization"].get("networkMode","restricted")/"model.sock"
        for _ in range(30):
            if gateway.is_socket(): break
            time.sleep(0.1)
        else: raise SystemExit("Task gateway is unavailable")
        os.environ["HOME"] = str(ROOT)
        os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        # Path validation and argv construction can fail before OpenShell starts.
        # Keep them inside the restoration boundary so a rejected local path
        # cannot leave the WebUI unable to traverse its conversation storage.
        spec=openshell_runner.task_spec(request["taskId"],request["owner"],request["authorization"],request["provider"],request["model"],request["thinking"],request["sessionId"],request["fork"],ROOT/"users",ROOT/"openshell-image-digests.json",ROOT/"openshell-policies")
        sandbox, policy_path = spec["name"], spec["policy"]
        child = subprocess.Popen(spec["create"], start_new_session=True)
        if child.wait() != 0:
            raise SystemExit("OpenShell could not create the task sandbox")
        child = subprocess.Popen(spec["execute"], start_new_session=True)
        if stop_requested and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
        returncode = child.wait()
    finally:
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
