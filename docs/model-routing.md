# Adaptive effort and protected external inference

## Default behavior

Qwen 3.8 Flash-Next (`spark-qwen/qwen3.8-flash-next`) remains the local default.
Nemotron is disabled but retained for rollback; it must not implement nontrivial
code. Approved external models may implement code as well as plan or review it.
Profiles govern tool permissions, not a mandatory reasoning level.

**Auto · agent chooses** starts the parent at low effort for assessment in every
profile. It no longer matches coding/finance/CAD/BMC keywords to high effort.
The agent may complete routine work directly, or delegate a bounded subtask at
a selected effort/model:

```python
await rlm.spawn(
    "Implement the bounded change, run its tests, and return evidence.",
    name="implementation-1",
    model="spark-qwen/qwen3.8-flash-next",
    thinking="medium",
)
```

This is a real Python API inside IPython, not a model tool name. Medium is a
reasonable starting point for ordinary implementation/analysis; high is reserved
for harder uncertainty, repeated failed checks, or consequential review. These
are agent guidelines, not a deterministic classifier or a guarantee that the
agent always chooses optimally. The parent stays at its initial effort; different
effort is applied to the delegated child. Never spawn recursive routing chains
merely to decide how to route.

The running Qwen chat template supports **low, medium and xhigh** and itself
aliases high to xhigh. Therefore the existing wire map remains:
off -> none; minimal/low -> low; medium -> medium; high/xhigh/max -> xhigh.
There is no independent native high tier. Do not pretend that changing the
label introduces one. The server fallback remains low.

Explicit chat/project effort choices persist and override Auto; the injected
policy instructs local children to preserve that explicit choice. An external
model must receive a supported effort. Existing saved manual high settings are
not silently reset: choose Auto in the conversation header to adopt selection.

Effort does not increase decode throughput or guarantee correctness. All local
efforts use the same IQ4_XS weights and 262,144-token Q8 cache slot. Input and
output share that context; the task deadline is a separate control.

## Initial model routing

1. A coding task using the legacy Nemotron default is redirected to Qwen unless
   an explicit model request is present. Nemotron never wins a code route.
2. The first explicit slash directive selects its enabled target. Code requests
   no longer override /codex or a capable selected external default.
3. Existing enabled phrase rules apply in priority order. Legacy
   nemotron-default rules only apply when that model is selected.
4. Otherwise the selected default handles the task, then chooses bounded
   delegations as appropriate.

Enabled/configured is NOT synonymous with privacy-approved. Any external route
must pass the protected gateway even if a directive or phrase rule selected it.
A denied external request returns an actionable JSON error, not a silent transfer
to another provider. Nemotron's code restriction survives custom phrase rules.
Normal disabled-rule target fallback behavior remains visible.

## Agent-selected external delegation

Inside OpenShell the agent reads:

```python
import json, urllib.request
routes = json.load(urllib.request.urlopen(
    "http://127.0.0.1:31000/routing-models", timeout=10
))
```

Only exact IDs in `externalModels` are available for external delegation. The
agent chooses one when difficult implementation, architecture, capability limits
or an independent critique justify cloud latency/cost, and passes it as the
`model` argument to `rlm.spawn`. Supply the smallest relevant task packet,
exclude credentials/unrelated history, state a short model/effort/reason update,
and verify the actual result. No hidden reasoning should be displayed.

The implemented adapter is **openai-codex via ChatGPT OAuth**, not the OpenAI
API-key route. Additional configured providers are not automatically supported
in OpenShell: they require a reviewed gateway adapter and separate approval.
Do not invent IDs or bypass the gateway with direct URLs or copied credentials.

## Protected no-training approval

The root-managed `/etc/prime-agent/inference-policy.json` lists exact models per
owner, bound to a SHA256 fingerprint of the installed Codex account ID. Approval
requires an explicit no-training attestation, non-secret review evidence and an
expiry. The gateway checks file ownership/permissions, account identity, model
and expiry on each new cloud request, including after credential refresh.
Missing/malformed/unsafe/expired approvals fail closed. A credential alone does
not grant approval. Local inference is unaffected.

After independently verifying the account/workspace and applicable no-training
controls, an administrator may run:

```bash
sudo /usr/local/libexec/prime-approve-inference-route \
  --owner USERNAME --model gpt-5.6-sol \
  --review-days 30 --confirm-no-training \
  --evidence "Describe the actual account policy/settings review; no secrets"
```

Repeat --model only for exact supported models intended for delegation. This
command records an administrator's attestation; it does not inspect provider
settings, verify legal compliance or create a no-training guarantee. Do not run
it merely because login works. Account changes invalidate the previous approval.
Review periods are 1-90 days. Revoke with:

```bash
sudo /usr/local/libexec/prime-approve-inference-route --owner USERNAME --revoke
```

Policy changes are read on new requests without restarting the gateway. They
do not retract already-sent requests or cancel an existing stream. Previous
approval files are retained root-only for recovery. No provider credentials are
printed, copied to the policy or exposed in the catalog.

**Limits:** no-training is not zero retention. This gate covers model requests
through the protected OpenShell model socket; it is not general network DLP,
perfect redaction, or enforcement of a provider's promises. Browser/search/upload
destinations and native host sessions need their own controls. Auxiliary cloud
model calls through this socket have the same checks. Task tools do not gain
authority to publish, trade, reboot, widen networking or approve providers.

## Installation and validation

The OpenShell installer installs inference_policy.py and the administrator
approval helper alongside the model gateway, but never creates approval or
overwrites an existing policy. Install the updated gateway and dashboard
together while agent tasks are idle; restart those services after the files are
installed. Qwen does not require a restart or a model/image rebuild.

Managed workspace instructions and both public policy templates must match.
Do not overwrite unrelated project instructions. Existing chat/project manual
settings and custom phrase rules are preserved.

Run `bash scripts/validate-release.sh` for routing, UI syntax, gateway HTTP and
policy regressions. Run `validate-qwen-effort.mjs` in the deployed runtime image
to verify low/medium/high/off wire values without external inference. Run
`validate-qwen-task.py` only while production tasks are idle for a real
OpenShell smoke test. It uses synthetic prompts and no external account.
