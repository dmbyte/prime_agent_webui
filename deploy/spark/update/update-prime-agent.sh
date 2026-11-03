#!/usr/bin/env bash
set -euo pipefail

status_dir="${HOME}/.prime/agent/update-status"
status_file="$status_dir/agent.json"
phase="preflight"
failure_reason=""
download_dir=""
write_status() {
  local result=$1 exit_code=$2 temporary
  install -d -m 0700 "$status_dir"
  temporary=$(mktemp "$status_dir/.agent.XXXXXX")
  /usr/bin/python3 - "$result" "$exit_code" "$phase" "$failure_reason" >"$temporary" <<'PY'
import datetime, json, sys
print(json.dumps(dict(ran=True, result=sys.argv[1], exitCode=int(sys.argv[2]),
    phase=sys.argv[3], reason=sys.argv[4],
    updatedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())))
PY
  chmod 0600 "$temporary"
  mv -f "$temporary" "$status_file"
}
finish() {
  local code=$?
  trap - EXIT
  if [[ -n $download_dir ]]; then rm -rf -- "$download_dir"; fi
  if (( code == 0 )); then
    failure_reason=""
    write_status success 0
  else
    failure_reason=${failure_reason:-"Prime Agent update failed during ${phase} (exit ${code}). Check the update service log; the task images were not changed."}
    echo "$failure_reason" >&2
    write_status failed "$code"
  fi
  exit "$code"
}
# A second caller must not overwrite the running updater's status.
install -d -m 0700 "$status_dir"
exec 9>"${HOME}/.prime/agent/prime-update.lock"
flock -n 9 || { echo "Another Prime update is already running." >&2; exit 75; }
trap finish EXIT
write_status running 0

runtime_link="${HOME}/.local/share/prime-agent-node/current"
runtime=$(readlink -f "$runtime_link")
test -x "$runtime/bin/node"
test -x "$runtime/bin/npm"
export PATH="$runtime/bin:/usr/local/bin:/usr/bin:/bin"

package_version() {
  /usr/bin/python3 - "$runtime/lib/node_modules/prime-agent/package.json" <<'PY'
import json, re, sys
with open(sys.argv[1]) as source:
    package = json.load(source)
version = package.get('version', '')
if package.get('name') != 'prime-agent' or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[+-][A-Za-z0-9.-]+)?', version):
    raise SystemExit('Installed Prime package identity/version is invalid')
print(version)
PY
}

cli_version() {
  local output
  # The first invocation of an npm bridge can install the native payload and
  # print migration progress. Do not compare that transcript with the version.
  if ! output=$(timeout 180s "$runtime/bin/prime-agent" --version 2>&1); then
    echo 'Prime Agent CLI verification failed or timed out; runtime activation is not verified.' >&2
    return 1
  fi
  printf '%s\n' "$output" | /usr/bin/python3 -c '
import re, sys
versions = set()
for line in sys.stdin:
    match = re.fullmatch(r"(?:prime-agent\s+)?v?([0-9]+\.[0-9]+\.[0-9]+(?:[+-][A-Za-z0-9.-]+)?)", line.strip())
    if match: versions.add(match[1])
if len(versions) != 1:
    raise SystemExit("Prime CLI did not return one unambiguous version")
print(versions.pop())'
}

before=$(package_version)
phase="release lookup"
release_tag=$(gh api repos/PrimeIntellect-ai/prime-agent/releases/latest --jq .tag_name)
[[ $release_tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+([+-][A-Za-z0-9.-]+)?$ ]]
release_version=${release_tag#v}
echo "Updating Prime Agent host tools from ${before} to release ${release_tag}; OpenShell task images stay pinned."
if [[ $before != "$release_version" ]]; then
  phase="artifact download"
  artifact="prime-agent-${release_version}.tgz"
  release_base="https://pub-728493de92a943e2a9b2d17b4719f318.r2.dev/releases/${release_tag}"
  download_dir=$(mktemp -d "${TMPDIR:-/tmp}/prime-agent-update.XXXXXX")
  curl -fsSL "$release_base/$artifact" -o "$download_dir/$artifact"
  curl -fsSL "$release_base/SHA256SUMS" -o "$download_dir/SHA256SUMS"
  phase="checksum verification"
  checksum=$(awk -v artifact="$artifact" 'length($1)==64 && $1 !~ /[^a-f0-9]/ && $2==artifact && NF==2 {print}' "$download_dir/SHA256SUMS")
  [[ -n $checksum && $checksum != *$'\n'* ]]
  printf '%s\n' "$checksum" | (cd "$download_dir" && sha256sum --check --strict -)
  phase="package installation"
  npm install --global --prefix "$runtime" "$download_dir/$artifact"
fi
phase="package verification"
installed=$(package_version)
[[ $installed == "$release_version" ]]
phase="CLI activation and verification"
after=$(cli_version)
if [[ $after != "$release_version" ]]; then
  failure_reason="Prime package ${release_version} is installed, but the CLI reports ${after}. Migration/fallback needs attention; task images were not changed."
  exit 1
fi
phase="complete"
echo "Prime Agent host update verified: ${before} -> ${after}. OpenShell task images unchanged."
