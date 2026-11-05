# Installation observation and exact console steps

Use Network operations with LAN/Full access and an owner-configured saved
connection. Never search transcripts or files for credentials. The helper uses
the fixed task broker; TLS exceptions and target scope remain owner settings.

```python
b = BMCWorkflow('/project')
b.connections()  # choose redfish and KVM connections by observed IDs and names
b.inspect(redfish_connection)  # enumerate systemIds, no automatic first selection
b.inspect(redfish_connection, system_id='1')  # only a discovered ID
```

Inspection is GET-only. It returns current power, boot override, and virtual
media booleans/enums. No image URLs, serials, names, OEM strings or credentials
are returned. A configured image or inserted media does not prove that the ISO
is reachable, correct, or booted. Missing media advertisement is `not-advertised`,
not empty/ejected. Unknown fields remain unknown. Unsupported/paginated or
off-target resource links fail closed. Systems with nonstandard OEM media need
an independently reviewed adapter; do not fall back to arbitrary HTTP.

For ISO hosting, use `lan-web-host` and verify the intended file size/hash and
URL separately. Mount, optical one-time boot and readback-gated restart use the
separate adapter in [bmc-controls.md](bmc-controls.md); read access never grants
those changes. There is no automated installer sequence.
Existing saved-console input is available through this exact-approval helper:

```python
b.open_console('console-v1', kvm_connection)
b.capture('console-v1', 'before.png')  # inspect the image before deciding input
b.key('boot-menu-v1', 'console-v1', 'f9')
```

This saves one request ID before contacting the broker. If approval is required,
ask the owner to approve that exact action in Settings → My connections. Then
call the **same** `key` invocation to consume it. Do not approve it yourself.
Repeated calls after dispatch read the retained result; no input is replayed.
For transport loss, interruption or uncertain receipt:

```python
b.action_receipt('boot-menu-v1')  # read-only broker reconciliation using original ID
b.capture('console-v1', 'after.png')
```

An acknowledged receipt is not proof of BIOS/boot effect. Inspect fresh evidence
before the next action. No blind key sequences, password entry, automatic reset,
or fresh-ID retries. An unavailable/expired session or old task grant is a stop,
not permission to reopen. `close_console('console-v1')` closes only that handle.
The helper supports named keys, not arbitrary text or browser scripting.
Workspace receipts are untrusted recovery data and never restore capabilities.
