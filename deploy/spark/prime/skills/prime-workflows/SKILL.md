---
name: prime-workflows
description: Run recoverable coding build/test/artifact/preview steps or BMC ISO installation controls with saved connections and per-action approvals. Use for application verification and server installation workflows in Prime.
---

# Prime workflow adapters

These helpers reduce repeated generated tool code. They use the current task's
workspace and permissions, not a new agent or privileged execution route.

In IPython, import the script from this skill's `scripts` directory (use the
actual skill path if project selection loaded a versioned shared generation):

```python
import sys
sys.path.insert(0, '/home/prime/.prime/agent/skills/prime-workflows/scripts')
from prime_workflows import CodingWorkflow, BMCWorkflow
```

Read [coding.md](references/coding.md) for build/test commands, artifact hashes
and LAN previews. Read [bmc.md](references/bmc.md) for boot/media inspection and
durable KVM request IDs, and [bmc-controls.md](references/bmc-controls.md) only
when mounting/ejecting an ISO or changing one-time boot/restarting is requested.
Do not load all guides for unrelated tasks. Invoke these scripts through Prime's
`ipython` tool, not a guessed `bash` tool; they are not pre-imported packages.

Use a distinct, meaningful step ID for each intended action. Reusing the same
step returns its retained result, not a fresh execution. An `unknown` result
requires inspection and user direction; never invent a replacement ID merely
to retry. These workspace records are recovery aids, not approvals or a secure
audit ledger. Broker approvals remain authoritative. No passwords in command
arguments, console text, step names, or published files.

If a reviewed helper fails, report its error and stop that workflow. Do not edit
the installed helper, remove its records or monkey-patch it to obtain a passing
result. Propose a reviewed source fix and use a fresh version only after testing.
