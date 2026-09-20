---
name: ipmi-redfish-bmc
description: Read server health, inventory, firmware, sensors, and power state through standards-based Redfish or ipmitool, with explicit confirmation gates for power-changing operations.
---

# IPMI and Redfish BMC

Use this skill in the `network-operations` OpenShell profile with LAN access.
Prefer Redfish for portable inventory and health queries; use `IPMIClient` only
when the target requires IPMI. Supply credentials at runtime and never persist or
log them. TLS verification defaults on; disabling it for a self-signed BMC is an
explicit per-client choice.

Read-only status, inventory, firmware, and sensor queries are allowed within the
task's authorized target. Power actions require explicit user authorization for
the exact target and action, followed by `confirm=True`. The library passes the
IPMI password through `IPMI_PASSWORD` to `ipmitool` rather than its command line.

```python
from ipmi_redfish_bmc import RedfishClient

bmc = RedfishClient("https://bmc.example", username, password, verify_tls=False)
print(bmc.system())
```
