#!/usr/bin/env bash
set -euo pipefail

test "${EUID}" -ne 0 || { echo "Run as the WebUI owner, not root." >&2; exit 2; }
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
nvidia_commit=fd9f1466ff8a39178e488981e8b5118709392949
source_checkout=""
bundled_only=false

while (($#)); do
  case "$1" in
    --bundled-only) bundled_only=true ;;
    --nvidia-source) shift; source_checkout=${1:?Missing path for --nvidia-source} ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

for command in git python3 sudo; do
  command -v "$command" >/dev/null || { echo "Missing skill installer prerequisite: $command" >&2; exit 1; }
done

staging=""
cleanup() { [[ -z $staging ]] || rm -rf "$staging"; }
trap cleanup EXIT

arguments=(
  --owner "$USER"
  --bundled "$repo/deploy/spark/prime/skills"
)
if [[ $bundled_only != true ]]; then
  if [[ -z $source_checkout ]]; then
    staging=$(mktemp -d)
    git clone --filter=blob:none --no-checkout https://github.com/NVIDIA/skills.git "$staging/nvidia-skills"
    git -C "$staging/nvidia-skills" checkout --detach "$nvidia_commit"
    source_checkout="$staging/nvidia-skills"
  fi
  arguments+=(--nvidia-source "$source_checkout")
fi

sudo python3 "$repo/deploy/spark/prime/install-managed-skills.py" "${arguments[@]}"
