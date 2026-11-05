# Authenticated task supervision and recovery

This is the first reliable-assistant-core stage after the FP4 promotion. It
strengthens the existing Prime/OpenShell execution path; it does not introduce
a second agent framework or change the model, task images or cloud policy.

## API identity

Every data/action request to the dashboard API now verifies the browser session
with the fixed local authentication service. Caller-supplied `X-Prime-User` and
`X-Prime-Role` are overwritten with authenticated identity/current account role.
Missing, expired, disabled and deleted accounts fail closed. Writes additionally
check CSRF against the server-side session; matching a caller-created CSRF
cookie/header is not sufficient. Existing origin checks remain enforced.

Nginx still performs its normal login checks. Direct loopback callers do not
bypass authentication. Auth-service failure returns an error rather than falling
back to headers. The shared host account/root remain trusted administrators;
this does not sandbox a malicious process already running as that account.

`GET /api/health` is deliberately unauthenticated and returns only `ok` and the
aggregate `activeTasks` count. It contains no identity, prompt, model, account,
credential or conversation data. Installation checks use this endpoint. An idle
count alone is **not** permission to restart: maintenance also holds the shared
exclusive admission lock and checks sandbox inventory and model metrics.

Old diagnostic scripts that fabricated identity/CSRF headers are no longer
valid production canaries. They fail closed. Use a real signed-in session or a
separate synthetic test server; do not add an impersonation bypass. The old
maintenance bootstrap refuses an API without the aggregate health contract;
such old installations need a reviewed idle-time API migration first.

## What is durable

Before spawning a runner, the API saves the original request, owner, project,
attachment IDs and relevant conversation settings. It checkpoints sanitized
runtime stages, ordered event numbers and typed tool-step states at event
boundaries, with a supervisory heartbeat approximately every five seconds.
Metadata writes flush both the file and parent directory. Storage is the
existing owner-protected `~/.prime/agent/webui-metadata.json`; no new database
service is needed for this stage.

Tool-step states have deliberately limited meanings:

| State | Meaning |
|---|---|
| `running` | A tool-start event was observed |
| `returned` | The tool returned without a reported tool error; target effect is not independently verified |
| `error` | A tool error was reported; side effects may still have occurred |
| `unknown` | Supervision ended while the tool was in flight; reconcile before continuing |

These checkpoints are observations, **not** action approvals or a replacement
for the saved-connection broker's durable action receipts. They retain no bearer
capabilities, environment, raw tool arguments/results or hidden reasoning.
The original prompt is retained as private user data, not public telemetry.
The latest 100 tool steps and 200 runtime events are bounded recovery summaries;
the existing redacted work log provides longer history. Native transcripts and
workspace artifacts remain in their existing storage.

## Failure and restart behavior

- Spawn/initial-prompt failures retain the request instead of deleting it.
- A clean process exit without an answer is not reported as successful.
- Monitor failure produces a deterministic runtime report, without requiring
  another model call or exposing exception text.
- On API restart, prior active checkpoints become failed/unverified records;
  in-flight steps become unknown and task connection grants are revoked.
- Recovery never resends a prompt, input, reboot, publication or tool call.
  An old external worker might still exist; inspect its actual state/receipt.
- A recovered request can be continued explicitly in a new task after review;
  old authorization and private-console sessions are not restored.
- The UI shows the runtime report outside the collapsible work log at its
  existing conversation position; step details remain available inside it.

Disk failure can still prevent persistence. This is not a full workflow engine,
automatic process reattachment, off-device backup or demonstrated power-loss
recovery. Successful tasks continue to use the native final answer. Existing
bounded in-session correction is separate from restart recovery.

## Installation and acceptance

Install matched `api.py`, `api_v2.py`, `auth.py` and `app-v2.js` using the normal
installer/update paths. The authentication service must be updated/restarted
before the API uses its new `/auth/check-write` contract. Activate only while
every user/task/sandbox is idle; retain prior source and protected metadata
backups. No model or task-image restart is required for this stage.

Run `scripts/validate-release.sh`. The synthetic real-HTTP suite covers forged
headers, current roles, disabled/deleted accounts, session-bound CSRF, auth
outage, cross-user records, pre-spawn persistence, broken stdin, monitor failure,
answerless exit and checkpoint restoration. With Playwright installed, run:

```bash
PYTHONPATH=deploy/spark/dashboard:deploy/spark/container \
  python3 deploy/spark/dashboard/validate-reliable-core-ui.py
```

Optionally set `PRIME_TEST_CHROME` to a local Chromium executable. This browser
fixture uses synthetic accounts, real local HTTP authentication and the actual
recovery-card renderer. It does not exercise the entire deployed WebUI or a real
BMC, and does not weaken production authentication for tests.

## Next capability stage

The [first dedicated workflow adapters](workflow-adapters.md) now provide coding
build/test results, artifact hashes, LAN previews, BMC boot/media observation and
recoverable exact-approved console steps. They do not implement automatic
Redfish mutations, a complete OS-installation workflow or a privileged workflow
engine. Continue with end-to-end workload acceptance and separately reviewed
write adapters before claiming unattended installation.
Keep mutation authorization outside generated code. Follow with restart/restore
drills, multi-user FP4 soak and workload-specific quality measurements before
additional resident models or autonomous skill promotion.
