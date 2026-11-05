# Qwen 3.8 Flash-Next FP4 / reviewed GB10 b12x runtime

This is the reference runtime promoted on November 5 after two passing
broker-aware agent/vision trials and a production-gateway smoke check.
Do not run it alongside IQ4 or Nemotron. It uses the same local provider/model ID
and endpoint as IQ4; task images, saved connections and cloud approvals do not
change. Keep the exact stopped IQ4 container/image/weights and its service.

## Exact profile

| Setting | Value |
|---|---|
| Weights | `diffbot/Qwen3.8-Flash-Next-FP4-Local-DGX-Spark` |
| Revision | `b22d249d5406c0720a3fdac16ca54f2ac3d8bf4b` |
| Runtime image | `eugr/spark-vllm-b12x@sha256:03a956544e9f9b4b7ba91690469fbe7848bdbef29a7d2e0f5788368467bb3595` |
| Provider / model | `spark-qwen` / `qwen3.8-flash-next` |
| Host endpoint | `127.0.0.1:30001`, never a public bind |
| Context / sequences | `262144` / `1` |
| GPU utilization / batch | `.76` / `8192` |
| Speculative drafts | MTP `4` |
| Cache precision | FP8 target KV / BF16 draft KV (not IQ4's Q8 KV) |
| MoE | Pinned recipe W4A16; `QP_MOE=0` because enabled path failed evaluation |
| PLE | Pinned recipe NVMe/io_uring, overlap/async and 2000µs keepalive defaults |
| Container | `vllm-qwen38`, user UID/GID, private IPC, bridge network, all capabilities dropped, no-new-privileges |
| Memory / swap cap | `98g` / `98g` (no container swap allowance beyond RAM cap) |
| Service | `vllm-qwen38.service`, bounded startup, Docker restart unless-stopped |

All other kernel/patch settings are the immutable recipe defaults, including
MXFP8 head, English draft vocabulary, BF16 expert activations, tail checkpoints,
prefill bundles and vision support. See the pinned downloaded `recipe/serve/serve.sh`
for the full switches; this is community-patched software, not stock vLLM.
The original launcher hash is verified before deriving a loopback-only launcher.
Images/weights/patches must not be silently updated independently.

The reference Spark reuses its verified staging directories rather than copying
102 GB: `model_dir=/home/dbyte/prime-model-eval-20261103/candidate` and
`cache_dir=/home/dbyte/prime-model-eval-20261103/candidate-cache`. Despite their
historical names these are now live dependencies: **do not delete them as test
cleanup**. Fresh installs should use the dedicated paths below. Task images
remain Prime 0.9.5; the host CLI is 0.10.2 and OpenShell is 0.1.6.

## Stage and install (does not switch models)

From the checked-out repository on the Spark, download/verify the pinned public
artifacts and exact image. This is about 102.27 GB plus images/caches; no user
content is sent to a model provider. Review licensing before downloading.

```bash
python3 evals/spark/stage_candidate.py --destination "$HOME/models/qwen38-fp4"
docker pull eugr/spark-vllm-b12x@sha256:03a956544e9f9b4b7ba91690469fbe7848bdbef29a7d2e0f5788368467bb3595
install -d -m 0700 "$HOME/vllm-qwen38" "$HOME/.cache/qwen38-fp4" "$HOME/.config/systemd/user"
install -m 0644 deploy/spark/vllm-qwen38/start.py evals/spark/prepare_trial.py "$HOME/vllm-qwen38/"
install -m 0644 deploy/spark/systemd/vllm-qwen38.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
```

Create `~/vllm-qwen38/runtime.json` containing exactly these two absolute paths,
substituting your home directory (JSON does not expand `$HOME`):

```json
{"model_dir":"/home/YOUR_USER/models/qwen38-fp4","cache_dir":"/home/YOUR_USER/.cache/qwen38-fp4"}
```

Previously verified model/cache directories may be reused; never overwrite
weights, compilation caches or trial evidence to hide a failed run. The starter
accepts no arbitrary environment flags and refuses a mismatched existing
production container. Changed settings require an explicit reviewed migration.
An existing matching container is started, never deleted/recreated implicitly.
Run `python3 ~/vllm-qwen38/start.py --check` before stopping IQ4; it verifies
configuration, pinned ARM64 image, launcher and container ownership without
starting or stopping anything. Missing-container errors are handled separately
from daemon/permission failures, which fail closed.
The Admin panel lists the FP4 service separately from retained IQ4/Nemotron;
restart requests are queued so a multi-minute model load does not become a
misleading 30-second HTTP timeout. A queued response is not a health confirmation.

## Activation and recovery

First pass the [matched acceptance gates](../../../evals/spark/README.md), then
hold Prime's existing exclusive maintenance admission while verifying every
user/task/sandbox and model request is idle. Save the original container ID,
image ID and enabled-service state. Stop the **exact recorded IQ4 container**,
start `vllm-qwen38.service`, wait for `/health` and verify `/v1/models`, short
text/tools/images, memory, gateway and UI. Only after success disable
`llama-qwen38.service` (without removing it) and enable `vllm-qwen38.service`.
Use an independent failure/stop hook that stops the new service and starts the
exact recorded IQ4 container if any step fails. Never start both engines.

For rollback, use the same idle admission, stop and disable the FP4 service,
verify IQ4's recorded ID/image still match, start that container directly,
wait for health, then re-enable its existing service. Do not use its old
`start.sh` just to recover the retained container: that script recreates it.
An intentional future IQ4 service restart may recreate it from retained files.

The installer for the WebUI does not automatically download/switch inference
engines. This explicit stage/activation procedure is required. Neither service
changes grants, no-training approvals, data routing, or private user storage.
