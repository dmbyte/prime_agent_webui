# Per-user skill credential setup

This branch adds **Settings → My credentials**. Saving is not automatic runtime
credential injection. A separately gated **My connections** pilot can consume
reviewed GitHub/Redfish requirements through bounded local read-only operations.
The read-only pilot is activated on the reference Spark. Additional isolated
browser/KVM/IPMI/SOL and native OpenShell HTTP paths are staged, not activated;
see [connection extensions](connection-extensions.md). Other tools still show
**tool integration pending**. See [connections](connections.md).
Do not claim a connection is tested or operational merely because it is Saved.

## User workflow

When an installed/enabled skill declares credentials, its reviewed fields appear
for the signed-in user. Project-only skills appear when selected in an owned
project. Enter the required values and save. Blank fields preserve existing
values; nonblank entries replace them. Saved values are never displayed or sent
back to the browser. Delete removes the local record, not the credential at the
remote service. Rotate/revoke a compromised credential at that service too.

Each credential also has **Ignore certificate errors**, off by default. This is
an owner-scoped encrypted setting, not a global switch or a field supplied by the
agent. It skips certificate expiry, hostname and CA-chain validation for direct
HTTP connections and the staged private browser/KVM adapters. An impersonating
server could receive your credentials; use it only for an endpoint you trust on
a controlled network. It does not enable old TLS protocols, weak ciphers, HTTP
downgrades, redirects or access to another target. Some obsolete servers can
still fail their TLS handshake.
The checkbox and direct-transport support are live on the reference Spark.
The private browser/KVM implementation is tested but remains runtime-disabled.

Save with the checkbox selected or cleared; blank password fields retain the
existing values. Changing this setting changes the credential revision and
invalidates existing grants/sessions. Renew the corresponding My connections
entry and start a new task. Existing records default to verification; older
clients that omit the setting preserve your saved choice. No existing account's
setting is automatically enabled by an update.

Prime's native OpenShell HTTP adapter does not implement this exception: it
rejects the request clearly before creating a provider and never silently falls
back to direct transport. The inspected proxy verifies upstream TLS independently
of its worker. IPMI/SOL does not use TLS, so this setting does not affect it.
Tools not integrated with saved credentials are not changed by this setting.

Disabling/removing a skill removes its active requirements. Existing saved entries
remain as inactive, delete-only records so users can clean them up. Changes to a
declaration create a new requirement rather than silently reusing old secrets.
Deleting a WebUI account removes its vault record before its username can be
reused. Disabling an account blocks access but retains its encrypted record.

Each user has independent values, even for the same skill/project requirement.
Neither project metadata, chat exports, skill ZIPs nor browser storage hold these
values. Do not paste credentials into chat or put them in a skill declaration.
There is no administrator web API for revealing another user's values.

## Declare a requirement

An uploaded skill ZIP can contain `credential-requirements.json` beside SKILL.md:

```json
{
  "version": 1,
  "credentials": [{
    "id": "service-login",
    "label": "Service account",
    "description": "A token for this service; use minimum required permissions.",
    "fields": [
      {"id": "username", "label": "Username", "required": true},
      {"id": "token", "label": "Access token", "required": true}
    ]
  }]
}
```

All fields are treated as secrets. No defaults, environment-variable destinations,
scripts, arbitrary URLs for fetching secrets, or automatic grants are accepted.
Limits: 16 credential groups per skill, 8 fields per group, 8192 UTF-8 bytes per
value and a 70,000-byte save request. IDs are lowercase identifiers, not paths.

Requirements are captured when the archive is submitted, displayed in the
administrator's review queue and enabled only after approval. The archive hash
is rechecked before installation. The auth service reads reviewed metadata,
never live task-writable skill files. The managed skill installer publishes
requirements in its metadata inventory; NVIDIA catalog manifests can carry the
same schema. Built-in BMC setup declarations are supplied separately in
`deploy/spark/prime/managed-credential-requirements.json`, without changing pinned
task images. Browser/KVM declarations remain setup-only. The management declaration
now advertises the `redfish-readonly` adapter; it does not enable IPMI/SOL,
browser login or server mutations. Adding this reviewed adapter changes the
requirement identity: old values become inactive and are not silently reused.
Resave under the new requirement, then explicitly create a scoped connection.

Personal inventories are owner-scoped. The installer publishes the
legacy `.prime/agent/skill-inventory.json`. A multi-user provisioner can publish
individual snapshots in `.prime/agent/skill-inventories/USERNAME.json` under the
WebUI service account's home; each file must identify that owner. Do not read
another user's inventory as a fallback. Uploaded, reviewed skills already use
the owner-scoped shared metadata catalog. A tool needs a reviewed skill/package
declaration; credentials are not inferred from free-form model text or all tools
on PATH. The managed publisher additionally writes a protected
`.prime/agent/global-credential-inventory.json` containing only installed,
distribution-managed built-ins with reviewed bundled declarations. These fields
are available to every WebUI user, including new accounts; values remain private
per user. Personal skill manifests are never copied into this global catalog.

## Storage and security boundary

The auth service, not the general dashboard API, handles `/auth/credentials`.
Every operation validates the actual login cookie and enabled user record; writes
also require that session's CSRF token. Forwarded user/role headers and JSON owner
overrides cannot select a vault. Responses expose only field/status metadata.
The feature fails closed unless `PRIME_CREDENTIALS_ENABLED=1` is explicitly set.

Files live in `skill-vault/` beside `web-auth.json`, normally
`~/.config/prime-agent/skill-vault/`. AES-256-GCM encrypts each user's payload with
a fresh random nonce and user-bound authenticated data. The directory is 0700;
master key and encrypted files are 0600. Symlinks, wrong ownership, unsafe modes,
corruption and missing keys fail closed. Writes are atomic and serialized within
the single auth service. Do not run multiple auth writers on the same vault.

Back up the key and encrypted records together into protected backup storage.
Never regenerate a missing key over existing data. Encryption does not protect
against root or the compromised host service account: that account holds the
key. This is not an external KMS, HSM, or protection from trusted host admins.
Deleting records does not erase old backups or revoke provider credentials.

The Advanced console is the shared host account, so both `/terminal/` and
`/terminal/ws` must enforce `/auth/check-admin` through the internal Nginx admin
check. Hiding a button is not sufficient. Ordinary users cannot be given this
host console while claiming cross-user credential isolation. Native/host agents
running as the service account are also trusted, unlike isolated OpenShell tasks.

## Installation / activation

The reference Spark's credential setup and read-only connection pilot were
activated in an idle window on October 24, 2026. Other installations still require
the explicit checks below. Keep active work running.
For a new installation, the root installer adds the distribution's
`python3-cryptography`, installs the protected console routes, and enables the
feature in the generated auth unit. With `--skip-packages`, install the dependency
for the service's `/usr/bin/python3` first; preflight checks it.

For an existing installation, schedule an idle maintenance window:

1. Preserve existing auth configuration, Nginx configuration and protected vault
   if present. Never copy real credentials into the repository.
2. Install the updated dashboard/auth Python modules and credentials.js asset.
   The normal WebUI updater copies them and requires cryptography, but does not
   automatically enable the feature or rewrite a customized Nginx configuration.
3. Merge the internal `/_auth_admin_check` location and both terminal guards from
   the reviewed Nginx template. Check `nginx -t`, reload, and verify a normal user
   is denied both the terminal page and WebSocket while an administrator succeeds.
4. Publish reviewed skill requirements with the managed installer or the normal
   upload/review flow. Do not execute unreviewed packages to discover credentials.
5. Only then set `PRIME_CREDENTIALS_ENABLED=1` in a prime-auth.service drop-in,
   reload the user service configuration and restart the auth service. Confirm
   persistence across reload and isolation with two test accounts.

Existing model-provider credentials and OAuth sessions are not migrated or
changed. This feature does not approve cloud inference or replace the independent
no-training approval policy. OAuth login/refresh and credential sharing are
follow-up work; multiple separately scoped named connections are supported. The
read-only connection pilot is activated separately, never by saving credentials.
Credential replacement/deletion invalidates its existing connections; resave the
connection to consent to the new credential revision, then start a new task.

## Verification

`bash scripts/validate-release.sh` includes vault/auth/manifest regressions and
JavaScript syntax checks. Use a virtual environment with cryptography if the
developer machine lacks the service dependency.

`python deploy/spark/dashboard/validate-credentials-ui.py` runs a real browser,
real HTTP auth handler and encrypted store against synthetic users on localhost.
It requires Playwright; `PRIME_TEST_CHROME` optionally selects a Chromium binary.
It uses a temporary browser profile and never logs in to production or calls a
model/BMC. Test credentials are synthetic and the temporary store is removed.
