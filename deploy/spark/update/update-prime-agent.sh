#!/usr/bin/env bash
set -euo pipefail

status_dir="${HOME}/.prime/agent/update-status"
status_file="$status_dir/agent.json"
write_status() {
  local result=$1 exit_code=$2 temporary
  install -d -m 0700 "$status_dir"
  temporary=$(mktemp "$status_dir/.agent.XXXXXX")
  printf '{"ran":true,"result":"%s","exitCode":%d,"updatedAt":"%s"}\n' "$result" "$exit_code" "$(date --utc +%FT%TZ)" >"$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$status_file"
}
finish() { local code=$?; if (( code == 0 )); then write_status success 0; else write_status failed "$code"; fi; }
trap finish EXIT
write_status running 0

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
