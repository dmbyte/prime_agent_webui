# Qwen 3.8 Flash-Next service

Qwen 3.8 Flash-Next is both the default orchestrator and implementation model
on the `only-qwen38flash` branch. It is served by a pinned llama.cpp build on `127.0.0.1:30001` and
exposed to Prime through the local model gateway as
`spark-qwen/qwen3.8-flash-next`.

## Model files

The default environment expects the Qwen files under:

```text
/home/dbyte/models/qwen38-flash-next-ud-iq4-xs/
├── UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
├── UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf
├── UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf
├── mmproj-F16.gguf
└── MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
```

If the files live elsewhere, edit `~/llama-qwen38/llama.env` after copying the
template. Do not commit downloaded model artifacts.

## Build and install

Prerequisite: a clean source checkout at commit
`560abb6616eea7b8c0fc76259bc08142df5c2e1b` under
`~/src/llama.cpp-qwen38-mtp`, or set `SOURCE_DIR` to that checkout. This is the
reviewed MTP/direct-read build used by the deployment, not an arbitrary upstream
latest revision. `build-image.sh` checks its Git revision and clean worktree;
it does **not** fetch source or model artifacts. Obtain the exact reviewed
source and weights before following this recipe; the repository alone is not a
self-contained model distribution. Docker with NVIDIA GPU support is required.

The following commands are for a fresh installation. Existing dual-model
installations must disable Nemotron before restarting Qwen with these larger
settings; follow the migration in the [root README](../../../README.md#dgx-spark-openshell-and-local-models).

The image build is pinned to a reviewed llama.cpp revision with the Qwen 3.8 MTP
support used on the Spark:

```bash
deploy/spark/llama-qwen38/build-image.sh
install -d ~/llama-qwen38
cp deploy/spark/llama-qwen38/llama.env.template ~/llama-qwen38/llama.env
# Set MODEL_DIR in llama.env to your staged model directory before continuing.
cp deploy/spark/llama-qwen38/start.sh ~/llama-qwen38/start.sh
install -m 0644 deploy/spark/systemd/llama-qwen38.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now llama-qwen38.service
```

## Defaults

- Image: `local/llama-qwen38-mtp:560abb66`
- Served model name: `qwen3.8-flash-next`
- Port: `30001`
- Context: `262144` (total input plus output)
- KV cache: `q8_0` K/V; model weights stay IQ4_XS
- Default effort: `low`, with high/xhigh requests mapped to native `xhigh`
- Batch / micro-batch: `2048` / `512`
- Loading: mmap with `--lazy-mode on-direct`
- Speculative draft head: shared-Q8 MTP
- Speculative draft tokens: `2`

The lazy direct-read setting keeps the PLE table on NVMe and pages it in on
demand. Nemotron is stopped and disabled for this expanded profile, with its
artifacts retained for rollback. Disable its Docker restart policy as well as its
systemd service. Retain one slot, automatic Prime compaction and the 15%
available-memory gate; validate long-context workload memory after any change.
Prime's host and sandbox catalogs must both advertise context 262144 and enable
reasoning effort forwarding. See the root recipe and model-routing guide for
the backed-up migration and manual effort override behavior.

## Verify

```bash
systemctl --user status llama-qwen38.service
curl -fsS http://127.0.0.1:30001/v1/models
```

With no user task occupying the single model slot, run as the WebUI owner from
the repository root:

```bash
python3 deploy/spark/prime/validate-qwen-task.py
python3 deploy/spark/prime/validate-qwen-context.py --long
```

The first test creates two synthetic conversations, verifies actual Prime model,
context and effort state, and checks an in-memory Python function with assertions.
It does not contact a BMC or external service. Archive those test chats afterward
if desired. The second measures short low/high responses, then a roughly
250K-token chat-format recall check and one-second memory samples. It can take
around 15 minutes on this Spark; it fails below the 15% MemAvailable reserve.
This is not an exhaustive accuracy benchmark or a multi-user capacity guarantee.

The endpoint must remain loopback-only. Qwen 3.8 is the only shipped Qwen local
runtime in this branch.
