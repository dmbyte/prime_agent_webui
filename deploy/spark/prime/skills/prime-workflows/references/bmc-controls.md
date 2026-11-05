# Approval-gated ISO installation controls

Requires a **separate** saved `redfish-install` connection, Direct trusted broker
transport, administrator runtime activation and Network operations with LAN/Full.
The existing read-only connection cannot make changes. Saved target credentials
and TLS exceptions remain owner settings; never supply passwords in arguments.

Use `b.connections()` and `b.inspect(connection)` to select the intended system,
then inspect that system's media. Confirm the correct ISO and intended target
with the user. ISO hosting is separate: use the managed `lan-web-host` skill for
deliberately public content. This adapter accepts only credential-free HTTP(S)
private-IPv4 `.iso` URLs with plain paths, no query/fragment/percent encoding or
target-BMC self-reference. Check the source file hash and intended client access.
The broker never forwards BMC credentials to the ISO URL, but the BMC fetches it.

Submit **one** action, return its approval request to the owner, and pause. The
owner approves that exact request in Settings → My connections → Console and
BMC action approvals. Only then repeat the identical invocation with the same
step ID. Never self-approve, submit a batch or automatically chain the next step.

```python
b.mount_iso('mount-iso-1', installation_connection,
    system_id=observed_system_id, media_resource=observed_media_resource,
    image_url=approved_iso_url)
```

Mount refuses occupied/unknown media rather than implicitly replacing it.
After owner approval and acknowledgement, inspect again. `acknowledged` does not
prove image content or boot success. Standard media actions and ETags must be
advertised by the BMC. Unsupported OEM-only operations fail closed.

```python
# Separate owner approval, only after acknowledged mount and fresh readback:
b.boot_iso_once('boot-iso-1', installation_connection,
    system_id=observed_system_id, media_step='mount-iso-1', mode='UEFI')
# Separate owner approval, only after acknowledged boot setting and readback:
b.restart_for_iso('restart-iso-1', installation_connection,
    system_id=observed_system_id, boot_step='boot-iso-1', reset_type='GracefulRestart')
```

Choose `UEFI` or `Legacy` for the intended installer; never guess. Boot is optical
`Cd`, one-time only. Restart requires that same mounted image to remain inserted
and write-protected, and the approved boot mode/override to match fresh readback.
Only `GracefulRestart` on an On system or `On` on an Off system is supported;
no force reset/off, boot-order editing, OS install automation or arbitrary HTTP.

Eject is also a distinct change requiring approval. It can break a running
installer; do not infer permission to eject merely because boot was observed:

```python
b.eject_media('eject-iso-1', installation_connection,
    system_id=observed_system_id, media_resource=observed_media_resource)
```

If state changes while approval is pending, authorization expires, a reply is
lost, or the BMC returns asynchronous `202`, stop. Read-only reconciliation:

```python
b.installation_receipt('mount-iso-1')
b.inspect(installation_connection, system_id=observed_system_id)
```

Never replace an unknown request ID to retry. The broker consumes approval
durably before sending; later attempts return its receipt, not another write.
Unknown/asynchronous receipts cannot authorize a later boot/restart even if an
image appears mounted. Ask for manual review; no automatic receipt promotion.
After a restart, inspect a fresh authorized KVM/SOL capture before any console
input. Firmware actions acknowledged over HTTP are not proof of OS installation.
