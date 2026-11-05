# HTML5 BMC console compatibility

Prime uses observed console capabilities rather than a single iLO generation.
The managed `bmc-html5-kvm` skill and private connection worker recognize these
English-language layouts:

| UI family | Reviewed launch controls |
| --- | --- |
| HPE iLO | HTML5 / HTML5 Integrated Remote Console |
| Dell iDRAC | Launch Virtual Console / Start Virtual Console / eHTML5 Console |
| Supermicro | Launch Console / iKVM / iKVM/HTML5 |
| Lenovo XClarity | Launch Remote Console / Start Remote Console |
| Generic | Explicit HTML5 or noVNC Console |

The worker supports same-origin frames and popups, bounded console-navigation
steps, and new visible canvas or video renderers. It excludes existing dashboard
charts and stops on ambiguous controls. Branding selects reviewed controls; it
never grants permissions. Firmware layout, license and HTML5 availability still
matter: this is not a claim that every model or firmware version has been tested.

Use the lazy `prime-workflows` helper to retain the console-open result and
`console_status` to inspect vendor family, renderer and readiness. An unsupported
layout returns `compatibility-blocked` with a bounded stage/reason, not raw page
text or credentials. Reusing the step returns its retained result, not another
login attempt. See the [skill reference](../deploy/spark/prime/skills/bmc-html5-kvm/references/compatibility.md).

## Boundaries

Traffic remains pinned to the exact saved IPv4 target using HTTPS/WSS port 443.
The worker does not enable console licenses, change default console preferences,
accept security dialogs, force session takeover, download plugins, use Java or
ActiveX, or bypass MFA/SSO. Other ports/origins, unknown layouts and ambiguous
login controls need a reviewed extension. Saved target certificate policy is
unchanged; a compatibility failure never disables verification automatically.

Saved connections remain owner/project/task-scoped. Console input needs a separate
exact owner approval. HTML5 support does not imply virtual-media or power API
support. Read-only observation handles bounded legacy HPE links, but
[installation writes](bmc-installation-controls.md) still require standard
advertised actions and prerequisites; no guessed OEM fallback is provided.

## Installation and evidence

Normal installation/update copies the dashboard modules and publishes the managed
skills. Existing installations must activate matched `connections.py`,
`connection_browser.py`, `connection_browser_worker.py`, `connection_sessions.py`,
managed policy and shared skill generation while all users' tasks, sandboxes and
model requests are idle. Back up these files and the registry/inventory pointers;
restart auth, dashboard API and connection broker only. No model, gateway or
task-image rebuild/restart is needed. Existing tasks do not gain new grants.
Restore matched files/pointers while idle for rollback; never restore old user
work or approvals over new records. Base setup: [private connections](connection-extensions.md).

Validation includes 565 regression tests on both development host and Spark,
ten real-Chromium synthetic console variants (including inline, popup, navigation
and video), and an isolated OpenShell broker/worker fixture with retained
captures, one approved synthetic key, lost-reply handling and no replay. A
GET-only legacy iLO preflight verifies media discovery, not installation writes.
Further live hardware tests were deferred at the owner's request. Other vendor
firmware remains unverified; `hardwareCertified=false` is intentional.

Vendor references: [HPE schema migration](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/ilo5/ilo5_adaptation),
[Dell virtual console](https://www.dell.com/support/kbdoc/en-us/000179797/dell-poweredge-idrac-virtual-console),
[Supermicro IPMI guide](https://www.supermicro.com/manuals/other/IPMI_Users_Guide.pdf),
[Lenovo XClarity overview](https://pubs.lenovo.com/xcc/dw1lm_c_ch1_introduction).
These describe vendor capabilities, not certification of Prime's adapter.
