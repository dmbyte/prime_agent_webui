# Build, test, artifacts, preview

Choose commands from the actual project and user request; the helper does not
install dependencies or guess a package manager. Development profile is usual.

```python
w = CodingWorkflow('/project')
result = w.run('unit-tests-v1', ['python3', '-m', 'unittest', 'discover'],
               directory='app', timeout=120, artifacts=['app/report.json'])
print({k: result.get(k) for k in ('state', 'exitCode', 'artifacts', 'outputTruncated')})
```

Arguments are an explicit list, never shell syntax. A deliberately requested
shell/interpreter is still executable code; this is not a new sandbox. The
existing OpenShell limits apply. Timeout is 1–3600 seconds. Output is drained
but retained only up to 64 KiB, inside the private result record. It can contain
private project data: inspect it locally and redact before reporting. Task
capabilities and provider keys are not inherited by the child; the task's
configured proxy remains available. Interactive prompts are disabled.

`passed` means exit 0 and all declared files could be hashed, **not** overall
application correctness or proof that this command created the files. Use fresh
build outputs when provenance matters. `failed`, `timed-out`, `artifact-error`,
`not-started`, and `unknown` are not success. Killing a command's process group
does not undo side effects or contain daemonized descendants. Do not run
background services through `run`; use the hosting broker below.

Some sandboxes deny process-group signals even after a successful command.
`cleanupVerified=false` records that limitation separately from exit status;
`cleanup.leaderExited` reports whether the direct child exited. On timeout with
unverified cleanup, stop and report it; the task lifecycle remains responsible
for sandbox cleanup. Do not weaken sandbox policy or retry in a new process.

```python
w.receipt('unit-tests-v1')  # no command execution
w.artifacts(['app/dist/index.html'])  # current size + SHA-256, regular files only
```

Artifacts must remain within the workspace, without symlink components, at most
128 files and 2 GiB total. Journals are in `.prime-workflows/`, mode 0700/0600;
retain them with the workspace, never place them in a published directory.
Do not overwrite failed receipts. After diagnosing and intentionally changing
code, use a new step ID for the new test attempt and explain what changed.

## User-requested LAN preview

Load `WebHost` from the installed `lan-web-host/scripts/prime_web_host.py` as
described by that skill. Stage only intended public content under
`/project/hosted/`, then:

```python
preview = w.preview('preview-v1', host, name='demo', directory='hosted/demo',
                    command=['node', 'server.js'], ttl_hours=24)
```

Omit `command` for static files. The helper requires a dedicated directory below
`hosted/`; inspect its contents before publishing. Files are accessible without
login on the LAN. No auto-launch after a test, no auto-retry after a lost reply.
On unknown result, inspect `host.list()` before considering another launch.
The returned URL must be an external RFC1918 IPv4 address, not localhost or a
task-container address. It is the broker's advertised address, not proof of
client reachability; verify from the intended client. Project scope is discovery
and control, not HTTP access control. Renew/stop through `WebHost` explicitly.
