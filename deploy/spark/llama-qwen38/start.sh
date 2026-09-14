#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/llama.env"

image="${IMAGE:-local/llama-qwen38-mtp:560abb66}"
container="${CONTAINER_NAME:-llama-qwen38}"
model_dir="${MODEL_DIR:-/home/dbyte/models/qwen38-flash-next-ud-iq4-xs}"
model_file="${MODEL_FILE:-UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf}"
mmproj_file="${MMPROJ_FILE:-mmproj-F16.gguf}"
mtp_file="${MTP_FILE:-MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf}"
port="${PORT:-30001}"

test -r "${model_dir}/${model_file}"
test -r "${model_dir}/${mmproj_file}"
test -r "${model_dir}/${mtp_file}"

docker rm -f "${container}" >/dev/null 2>&1 || true
exec docker run -d --name "${container}" --restart unless-stopped \
  --gpus all --ipc=host \
  --memory="${DOCKER_MEMORY_LIMIT:-88g}" \
  --memory-swap="${DOCKER_MEMORY_SWAP:-88g}" \
  --health-cmd="curl -fsS http://127.0.0.1:${port}/health || exit 1" \
  --health-interval=30s --health-timeout=5s --health-retries=5 \
  --health-start-period=300s \
  -p "127.0.0.1:${port}:${port}" \
  -v "${model_dir}:/models:ro" \
  "${image}" \
  --model "/models/${model_file}" \
  --mmproj "/models/${mmproj_file}" \
  --model-draft "/models/${mtp_file}" \
  --spec-type draft-mtp \
  --spec-draft-ngl "${SPEC_DRAFT_GPU_LAYERS:-999}" \
  --spec-draft-n-max "${SPEC_DRAFT_MAX_TOKENS:-2}" \
  --spec-draft-p-min "${SPEC_DRAFT_P_MIN:-0.0}" \
  --alias "${SERVED_MODEL_NAME:-qwen3.8-flash-next}" \
  --host 0.0.0.0 --port "${port}" \
  --ctx-size "${CONTEXT_SIZE:-32768}" \
  --parallel "${PARALLEL:-1}" \
  --gpu-layers "${GPU_LAYERS:-999}" \
  --flash-attn on \
  --cache-type-k "${CACHE_TYPE_K:-q8_0}" \
  --cache-type-v "${CACHE_TYPE_V:-q8_0}" \
  --batch-size "${BATCH_SIZE:-2048}" \
  --ubatch-size "${UBATCH_SIZE:-512}" \
  --load-mode mmap \
  --lazy-mode "${LAZY_MODE:-on-direct}" \
  --reasoning auto \
  --reasoning-format deepseek \
  --metrics
