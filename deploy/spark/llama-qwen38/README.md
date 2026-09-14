# Qwen 3.8 Flash-Next service

Qwen 3.8 Flash-Next is the supported local Qwen specialist for the DGX Spark
WebUI release. It is served by a pinned llama.cpp build on `127.0.0.1:30001` and
exposed to Prime through the local model gateway as
`spark-qwen/qwen3.8-flash-next`.

## Model files

The default environment expects the Qwen files under:

```text
/home/dbyte/models/qwen38-flash-next-ud-iq4-xs/
├── UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
├── mmproj-F16.gguf
└── MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
```

If the files live elsewhere, edit `~/llama-qwen38/llama.env` after copying the
template. Do not commit downloaded model artifacts.

## Build and install

The image build is pinned to a reviewed llama.cpp revision with the Qwen 3.8 MTP
support used on the Spark:

```bash
deploy/spark/llama-qwen38/build-image.sh
install -d ~/llama-qwen38
cp deploy/spark/llama-qwen38/llama.env.template ~/llama-qwen38/llama.env
cp deploy/spark/llama-qwen38/start.sh ~/llama-qwen38/start.sh
install -m 0644 deploy/spark/systemd/llama-qwen38.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now llama-qwen38.service
```

## Defaults

- Image: `local/llama-qwen38-mtp:560abb66`
- Served model name: `qwen3.8-flash-next`
- Port: `30001`
- Context: `32768`
- KV cache: Q8 K/V
- Batch / micro-batch: `2048` / `512`
- Loading: mmap with `--lazy-mode on-direct`
- Speculative draft head: shared-Q8 MTP
- Speculative draft tokens: `2`

The lazy direct-read setting keeps the PLE table on NVMe and pages it in on
demand. On the reference Spark, this was the practical way to keep Qwen 3.8
resident alongside Nemotron while preserving enough memory for OpenShell and the
WebUI.

## Verify

```bash
systemctl --user status llama-qwen38.service
curl -fsS http://127.0.0.1:30001/v1/models
```

The endpoint must remain loopback-only. Qwen 3.8 is the only shipped Qwen local
runtime in this release.
