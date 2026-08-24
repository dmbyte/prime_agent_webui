#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
set -a
source "${script_dir}/vllm.env"
set +a
: "${HF_TOKEN:?HF_TOKEN is required in vllm.env}"

image="${IMAGE:-vllm/vllm-openai:v0.27.1-aarch64-cu129-ubuntu2404}"
container="${CONTAINER_NAME:-vllm-nemotron35}"
port="${PORT:-30000}"

until docker info >/dev/null 2>&1; do sleep 2; done
docker rm -f "${container}" >/dev/null 2>&1 || true

exec docker run -d --restart unless-stopped \
  --name "${container}" --gpus all --shm-size 24g --ipc=host \
  --memory="${DOCKER_MEMORY_LIMIT:-68g}" --memory-swap="${DOCKER_MEMORY_SWAP:-80g}" \
  --oom-score-adj 500 -p "127.0.0.1:${port}:${port}" \
  -v "${HOME}/.cache/huggingface:/root/.cache/huggingface" -e HF_TOKEN="${HF_TOKEN}" \
  "${image}" "${MODEL_CKPT:-nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4}" \
  --host 0.0.0.0 --port "${port}" --moe-backend marlin --kv-cache-dtype fp8 \
  --enable-prefix-caching --spec-method dspark \
  --spec-model "${DSPARK_CKPT:-nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4-DSpark}" \
  --spec-tokens "${SPEC_TOKENS:-3}" --mamba-backend flashinfer --mamba-cache-mode align \
  --reasoning-parser nemotron_v3 --tool-call-parser qwen3_coder --enable-auto-tool-choice \
  --max-model-len "${MAX_MODEL_LEN:-65536}" --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.48}" \
  --kv-cache-memory-bytes "${KV_CACHE_MEMORY_BYTES:-12G}" --max-num-seqs "${MAX_NUM_SEQS:-2}" \
  --served-model-name "${SERVED_MODEL_NAME:-nemotron-3.5-lightning}"
