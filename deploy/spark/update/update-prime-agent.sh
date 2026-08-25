#!/usr/bin/env bash
set -euo pipefail

exec 9>"${HOME}/.prime/agent/prime-update.lock"
flock -n 9 || { echo "Another Prime update is already running." >&2; exit 75; }

runtime_link="${HOME}/.local/share/prime-agent-node/current"
runtime=$(readlink -f "$runtime_link")
test -x "$runtime/bin/node"
test -x "$runtime/bin/npm"
export PATH="$runtime/bin:/usr/local/bin:/usr/bin:/bin"

before=$(prime-agent --version)
echo "Updating Prime Agent from ${before}..."
npm install --global --prefix "$runtime" prime-agent@latest
after=$(prime-agent --version)
echo "Prime Agent update complete: ${before} -> ${after}"
