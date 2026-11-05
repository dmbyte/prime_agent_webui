# Dedicated workflow adapters

The managed `prime-workflows` skill adds deterministic helpers around the existing
Prime/OpenShell execution path. No extra model, resident agent, database, cloud
provider, task-image rebuild or new privilege is required. Detailed usage lives
with the [skill](../deploy/spark/prime/skills/prime-workflows/SKILL.md).

## Coding

`CodingWorkflow.run` takes a step ID, explicit command argument list, workspace
directory, 1–3600-second deadline and optional artifact paths. It retains exit
code, bounded output (64 KiB), timeout state, artifact sizes and SHA-256 hashes.
Children run in the existing task sandbox with noninteractive stdin, a separate
process group and a limited environment. The task proxy is preserved; saved
connection/hosting tokens and cloud provider keys are not copied into it.

The helper flushes a private record before starting. Repeating the same ID and
arguments returns the recorded result; changed arguments under that ID fail.
Interruption leaves an unknown outcome, never automatic replay. Timeouts kill
the same process group but cannot undo actions or contain a daemon that escapes
that group; this is not a replacement security sandbox. Build commands are code
and need the same user authorization as before. Artifact hashing proves current
file content, not authorship or whole-application correctness.

OpenShell may deny process-group signals. That must not discard a successful
command's result: the helper records `cleanupVerified=false` and separately
reports whether the direct child exited. On timeout it attempts a direct-child
kill and waits at most two seconds; denied cleanup stays explicitly unverified.
Stop and report a timeout with unverified cleanup; do not weaken sandbox policy.
Task sandbox teardown remains the final containment mechanism. Never patch an
installed helper or erase its receipts to manufacture a passing acceptance run.

LAN previews use the existing hosting broker and a dedicated `hosted/` directory.
They expose only deliberately published content, return the advertised LAN URL,
and retain that service reference. Unknown launch outcomes require registry
inspection; no duplicate launch or automatic cleanup is attempted. URL acceptance
does not demonstrate reachability from another VLAN or intended browser.

## BMC installation assistance

The saved `redfish-readonly` connection gains `redfish.installation`: enumerate
system IDs, then explicitly select one. Only GET is allowed. The broker projects
boot override, power and virtual-media state from observed same-target links,
with strict collection and response limits. It does not return image URLs,
serial numbers, OEM strings or secrets. A media link or `Inserted=true` is not
proof of correct ISO content or a successful boot. Fields follow the
[DMTF Redfish property definitions](https://redfish.dmtf.org/schemas/DSP2053_2026.1.html).

`BMCWorkflow` also retains KVM open/input request IDs before calling the existing
private console client. Named-key input still requires the owner's exact broker
approval; only the same pending request may resume after approval. Lost replies
and uncertain outcomes stop for read-only receipt lookup and a fresh capture.
Acknowledgement is not independently verified BIOS/installer effect. No automatic
first-system selection, blind key sequence, text/password entry, reset or reboot.

**Not implemented:** trusted Redfish media insertion/ejection, boot-setting PATCH,
reset, a complete unattended installation state machine, or vendor-wide hardware
certification. These require separate write authorization and acceptance tests;
do not use a raw-credential fallback to manufacture those capabilities.

## Installation, ownership and recovery

Normal installation/update publishes the skill through the immutable shared
registry, visible in the project skill catalog for all users. The new Python
script is loaded lazily from that skill directory; it uses the existing installed
private-console package. Personal skill directories are not overwritten by
shared publication. A user with a personal skill of the same name can select
the reviewed global generation explicitly in a project.

For an existing installation, stage and validate the repository first. Publish
reviewed shared skills with `install-managed-skills.py --owner <host-owner>
--bundled <checkout>/deploy/spark/prime/skills --publish-shared-only` as root.
Install matched `connections.py`, `connection_native.py` and
`connection_http_worker.py` in the dashboard directory, and the managed operating
policy in `/usr/local/lib/prime-runner/AGENTS.managed.md`. Only activate/restart
auth, API and connection broker after the maintenance admission lock plus
all-user task, sandbox and model idle checks. Retain previous files and registry
pointers for rollback. Do not restart active work or the model for this change.
New tasks provision the new shared skill; existing tasks do not gain new grants.

Records live in `.prime-workflows/` inside the user's workspace (0700 directory,
0600 files). Keep this private and include it in workspace backups. Output may
contain private project data, so redact before sharing. These same-user writable
files are recovery aids, **not a tamper-proof audit trail or authorization source**.
Host-owned broker approvals/receipts remain authoritative. Workspace restore
does not restore task credentials, approvals or external processes.

## Validation

Run `scripts/validate-release.sh`. Tests exercise real subprocess success/failure,
bounded output, missing artifacts, timeout/child termination, no replay after
restart, input/path validation, publication uncertainty, KVM approval ID reuse,
lost acknowledgement, and Redfish link/projection/GET-only constraints. Tests use
synthetic accounts and targets. No real BMC reboot, media mount, installer input
or investment transaction is part of this suite. A live task acceptance should
use synthetic files only and retain its result for review.
