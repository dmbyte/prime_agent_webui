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
release_tag=$(gh api repos/PrimeIntellect-ai/prime-agent/releases/latest --jq .tag_name)
[[ $release_tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+([+-][A-Za-z0-9.-]+)?$ ]]
release_version=${release_tag#v}
echo "Updating Prime Agent from ${before} to release ${release_tag}..."
artifact="prime-agent-${release_version}.tgz"
release_base="https://pub-728493de92a943e2a9b2d17b4719f318.r2.dev/releases/${release_tag}"
download_dir=$(mktemp -d "${TMPDIR:-/tmp}/prime-agent-update.XXXXXX")
cleanup_and_finish() {
  local code=$?
  rm -rf "$download_dir"
  if (( code == 0 )); then write_status success 0; else write_status failed "$code"; fi
}
trap cleanup_and_finish EXIT
curl -fsSL "$release_base/$artifact" -o "$download_dir/$artifact"
curl -fsSL "$release_base/SHA256SUMS" -o "$download_dir/SHA256SUMS"
checksum=$(grep -E "^[a-f0-9]{64}  ${artifact}$" "$download_dir/SHA256SUMS" || true)
[[ -n $checksum ]]
printf '%s\n' "$checksum" | (cd "$download_dir" && sha256sum --check --strict -)
npm install --global --prefix "$runtime" "$download_dir/$artifact"
after=$(prime-agent --version)
[[ $after == "$release_version" ]]
echo "Prime Agent update complete: ${before} -> ${after}"
