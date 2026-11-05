# HTML5 controller compatibility

The goal is capability-based support across controllers, not an iLO-version
whitelist. Detect the observed UI family and use reviewed visible controls;
never infer permissions, change console preferences or guess vendor endpoints.

Current worker recognizes iLO, iDRAC, Supermicro and Lenovo XClarity branding
and their reviewed English console-launch labels, plus explicitly labeled
generic HTML5/noVNC consoles. It handles same-origin popup/frame navigation and
new canvas/video renderers. A pre-existing dashboard chart is not a console.
Multiple candidate launchers/renderers stop as ambiguous. No forced takeover,
security-dialog acceptance, Java/ActiveX/download execution or default-console
type change is performed.

Use `prime-workflows`:

```python
result = b.open_console('console-v1', selected_kvm_connection)
# Only if result['state'] == 'opened':
status = b.console_status('console-v1')
b.capture('console-v1', 'before.png')
```

Status returns only family, renderer, readiness and boundary flags. It contains
no URLs, page text, cookies or credentials. `hardwareCertified=false` means a
successful open/capture is evidence for this session, not all hardware versions.
`compatibility-blocked` retains a stage/reason. Report it and ask for the relevant
hardware/firmware or reviewed adapter update; never self-patch the installed
helper or use raw browser tools to evade saved-connection controls.

Traffic remains HTTPS/WSS to the exact saved IPv4 target on port443, including
subresources and popups. A firmware requiring another hostname/port, plaintext
WebSocket, MFA/SSO, ambiguous login, special plugin or takeover is not silently
allowed. Report that requirement for explicit owner review. Do not alter its
network settings or disable security merely to make the test pass.

HTML5 availability/license and firmware-specific layouts are separate from
Redfish media/power operations. Read-only Redfish observation can resolve bounded
legacy HPE links, but this does not enable OEM mutations. A media slot shown
inserted is occupied; never replace/eject it because another slot is empty.
Each real console input/media/boot/power change still needs its exact approval.
