# Spark inference screening and candidate staging

This is an opt-in experiment, not a production installer or an autonomous
self-improvement loop. Keep the deployed IQ4_XS/Q8/256K engine as rollback.
Do not promote a model because it generates tokens faster on short prompts.

## What the suite measures

`spark-screen-v1` contains 100 synthetic cases: infrastructure/tool contracts
30, Python functions 25, CAD calculations 15, social publishing controls 15,
and portfolio arithmetic 15. Eighty development cases and 20 held-out cases
are separated by scenario family. Its SHA256 is frozen by the unit tests.
Do not edit prompts or grading after inspecting held-out results; use a new
version and new held-out cases if changes are necessary.

The cases do not contact BMCs, submit posts, access private records, place
orders or modify the host. Infrastructure tools are simulated fixtures.
Generated Python is graded in a disposable, immutable Docker image with no
network, mounts, GPU, privileges or writable root filesystem. The separate
grader also limits builtins and syntax, time, CPU, memory and process count.
Never call its `grade()` function on model-generated code directly on the host.

This is **contract screening, not 100 end-to-end agent tasks**. Several cases
explicitly state the desired policy response. It does not establish coding
repository quality, real CAD-kernel validity/fit, marketing effectiveness,
investment performance, visual understanding or production authorization.
Those require separate realistic artifact and sandbox evaluations.

Each run records exact suite/script hashes, configuration, visible responses,
strict fixture results, streamed latency, token usage and minimum available RAM.
Internal reasoning text is discarded. The decode rate is a stream-timing
estimate (chunks can contain multiple tokens); completion tokens divided by
total request time includes prompt processing and is **not** decode speed.
One short run is not a stable performance claim. Repeat matched tests and
report cold/warm cache state, long-context behavior and tail latency separately.

## Candidate pins

See `candidate.json`. The public
[FP4 Spark recipe](https://huggingface.co/diffbot/Qwen3.8-Flash-Next-FP4-Local-DGX-Spark/tree/b22d249d5406c0720a3fdac16ca54f2ac3d8bf4b)
is pinned to commit `b22d249d5406c0720a3fdac16ca54f2ac3d8bf4b` and its required
`eugr/spark-vllm-b12x` image digest. This is community-patched software, not a
claim of complete upstream vLLM support or an audited security boundary.
The download is approximately 102.27 GB decimal, plus container/cache space.
Review the model license and code before execution.

### Reference comparison — November 3, 2026

One completed run per engine on a GB10, driver 580.173.02, low reasoning effort,
temperature zero, one slot, identical synthetic prompts and grading. Candidate
results are for **QP_MOE disabled**, not the unmodified all-optimizations recipe.

| Measurement | Production IQ4_XS / llama.cpp | FP4 / b12x fallback |
|---|---:|---:|
| Configured context | 262,144 | 131,072 |
| Strict fixture matches | 96/100 | 97/100 |
| Python-function fixtures | 25/25 | 25/25 |
| Median estimated decode rate | 47.0 tokens/s | 77.0 tokens/s |
| Median visible first-response latency | 2.23 s | 1.74 s |
| Median coding-case duration, including grading | 7.41 s | 4.48 s |
| 95th-percentile model-request duration | 9.51 s | 6.47 s |
| Minimum available host RAM during screening | 33.40 GiB | 28.43 GiB |

This is encouraging: roughly 64% higher estimated decode rate and 40% shorter
coding-fixture duration. FP4 had about 5 GiB less headroom in these two recorded
runs, but the post-restart IQ4 smoke test had 43.75 GiB available: cached/retained
allocations materially affect this comparison. Do not infer a fixed 5 GiB model
footprint difference; cold/warm matched-context memory tests are still needed.
This run does **not** establish
a general accuracy improvement, 64% faster end-to-end Prime tasks, or suitability
for 256K use. Both engines missed the same three underspecified source-selection
schemas while making the requested safe choice; IQ4 also added extra fields to
one unsupported-claim response. No unsafe external action was executed.

The optimized QP_MOE path encountered a CUDA illegal-address error during
profiling. Disabling it passed that point and completed screening. The successful
fallback initialized in about 11.5 minutes with a partially populated compilation
cache. Warm-restart time was not measured. First-load compilation briefly left
about 19 GiB available in a sampled observation; serving memory was steadier.
The host watchdog did not report a sustained floor violation. Its allocated KV
pool was 172,533 tokens / 5.52 GiB, not enough for 262,144-token requests as-is.
Some additional kernel compilation occurred on initial inference requests.

The original production container was automatically restored after every trial,
and its healthy API was verified. No production model, provider or privacy setting
was changed. Before considering promotion: fix the ambiguous prompts in a new
suite version; repeat matched-context tests; validate 256K capacity/recall and
memory with realistic tools; test vision/video budgets and real Prime console/
browser flows; and verify repeated startup/recovery. Preserve the current engine.

Both measured runs used the same frozen suite, runner and grader source hashes.
Raw synthetic receipts and that benchmarked source are retained privately. The
subsequent published harness additionally rejects HTTP redirects and explicitly
selects the GPU-free `runc` grader runtime; the reference host already used runc.
These hardening changes passed unit tests, a real isolated grader check and a
guarded production-model smoke check; they were not used to regrade the scores.
All 435 repository/harness regression tests passed. The final production API
reported 262,144 context and one slot, with the original container/image identity.

`stage_candidate.py` uses public URLs without account tokens, verifies every
LFS SHA256 or Git blob SHA1 and writes a full receipt only after success.
Interrupted `.partial` files restart from the beginning, not from an unchecked
offset. Existing files must match the pinned digest. Never point staging at
a production model directory or a shared/untrusted writable directory.

```bash
python3 -m unittest discover -s evals/spark -p 'test_*.py' -v
python3 evals/spark/stage_candidate.py --destination /absolute/dedicated/candidate
docker pull eugr/spark-vllm-b12x@sha256:03a956544e9f9b4b7ba91690469fbe7848bdbef29a7d2e0f5788368467bb3595
python3 evals/spark/prepare_trial.py /absolute/dedicated/candidate
```

Preparation verifies the original launcher's SHA256 and creates a separate
derived launcher. It refuses to replace an existing container, publishes only
`127.0.0.1:30002`, runs as the cache's host UID/GID with a cache-local home,
uses private IPC, disables model downloads/telemetry, and caps
container RAM at 98 GiB without extra swap. Only the candidate model, isolated
cache and pinned patches are mounted. No credential vault or task workspace
is mounted. Docker network egress is not a complete security boundary.

On this GB10, Docker's memory accounting excludes much of the unified-memory
GPU allocation: during warmup it reported about 8 GiB while the host used about
94 GiB. The container limit is therefore **not a cap on total model memory**.
The host-wide MemAvailable watchdog is essential; inspect host statistics, not
just Docker's memory meter.

## Running a guarded experiment

This currently targets the reference Linux/Spark layout: user-owned Docker,
`llama-qwen38` on loopback 30001, Prime API 8765, the existing root-provisioned
OpenShell maintenance inode, all-user inventory and gateway `spark-local`.
Do not fabricate a new lock file to bypass an unavailable guard.

Copy these scripts into a dedicated trial root's `harness/` directory; stage
weights under its `candidate/`. Resolve a local Python-capable grader image to
its full `sha256:` image ID. The trial container must not already exist.
All downloads, image pulls and background builds must finish before timing.

Run the baseline with `maintenance_guard.py -- python3 run_screen.py ...`
in a **systemd user unit**, supplying `--label`, a new `--output` JSONL path,
and `--grader-image`. The guard takes an exclusive, nonblocking lease on the
existing admission inode, checks every user's active tasks, all OpenShell
workspaces and inference activity. Busy means stop preparation here—never
kill user tasks to obtain a benchmark window. While held, new tasks are denied
with the existing maintenance message; this is not a background benchmark.

`start_experiment.py` constructs the required bounded unit for either mode:

```bash
python3 /absolute/trial-root/harness/start_experiment.py --root /absolute/trial-root --grader-image sha256:FULL_IMAGE_ID
# Only after the control completes and all preparation is verified:
python3 /absolute/trial-root/harness/start_experiment.py --root /absolute/trial-root --grader-image sha256:FULL_IMAGE_ID --candidate --disable-qp-moe
```

The helper prints its exact unit name for `systemctl --user status` and
`journalctl --user -u`. A successful start means the job was dispatched, not
that startup, screening or recovery has passed. Inspect final logs and results.
The screen itself exits successfully when all requested cases were recorded;
individual fixture failures remain in the report. Completion is not a passing
quality gate and never triggers model promotion.

For the candidate, the unit's ExecStart must invoke the guard around
`candidate_trial.py --root /absolute/trial-root --grader-image sha256:...`.
Also configure **ExecStopPost** to run
`candidate_trial.py --root /absolute/trial-root --recover`, a bounded unit
runtime (e.g. 75 minutes), and enough stop time for production reload (e.g.
12 minutes). Monitor the unit and container logs. Do not launch the trial
without the independent recovery action.

The trial records the original container ID before stopping it, uses a
separate labeled container, waits up to 30 minutes for first-load compilation,
and restores the exact original container in `finally`. ExecStopPost provides
a second recovery attempt after process failure. It refuses ambiguous container
identities. A watchdog stops the candidate after three consecutive seconds
below 15% MemAvailable. This is a safeguard, not a guarantee against host OOM
or power loss. The production boot service remains enabled and unchanged.
After an abnormal stop, inspect the recovery marker and verify production
health before admitting more work. A stopped candidate is retained for logs;
do not force-delete an unfamiliar container to rerun the trial.

Initial candidate settings: 131,072 context, one slot, FP8 target KV, four MTP
drafts, 8,192-token prefill chunks and GPU utilization 0.73. Upstream patches
retain BF16 draft KV and direct NVMe PLE access. Low reasoning effort is requested
explicitly on both engines. The pinned vLLM protocol forwards it into the chat
template; the template defaults to xhigh when omitted.

The production control remains at 262,144 context with Q8 KV and two drafts.
Short identical prompts at these settings are an **as-configured diagnostic**,
not an equal-context comparison or evidence that FP4 meets the 256K requirement.
Before promotion, repeat at matched context/concurrency/effort, validate full
256K capacity and recall, real tool/browser/console flows, vision, memory reserve,
recovery and held-out task quality. Do not silently halve production context.

The optional `--candidate --disable-qp-moe` experiment disables only the
recipe's `QP_MOE` prefill optimization and labels its results separately. Use
it to investigate a startup failure in that path; do not silently count it as
the published all-optimizations recipe. Keep failed containers/logs and record
the precise variant. The Spark trial encountered a CUDA illegal-address error
during the first QP_MOE profile call; a single asynchronous error does not yet
prove which kernel or configuration caused it.

The strict score counts extra or differently named JSON fields as mismatches.
Three v1 source-selection prompts underspecify the field name, so inspect those
responses separately rather than treating a schema mismatch as an unsafe
decision. Keep the frozen score; fix prompt ambiguity in a new suite version,
not retroactively after examining results.

```bash
python3 evals/spark/summarize.py /absolute/results/control.jsonl /absolute/results/candidate.jsonl
```

Keep raw local evidence outside the public repository. Publish only reviewed
synthetic aggregate results with their limitations. No cloud routing, data
sharing approval, credential grant, model training or production promotion is
performed by these scripts.
