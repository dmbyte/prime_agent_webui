#!/usr/bin/env bash
set -euo pipefail

status_dir="${HOME}/.prime/agent/update-status"
status_file="$status_dir/openshell.json"
failure_reason=""
write_status() {
  local result=$1 exit_code=$2 temporary
  install -d -m 0700 "$status_dir"
  temporary=$(mktemp "$status_dir/.openshell.XXXXXX")
  jq -n --arg result "$result" --arg reason "$failure_reason" --arg updatedAt "$(date --utc +%FT%TZ)" --argjson exitCode "$exit_code" \
    '{ran:true,result:$result,exitCode:$exitCode,reason:$reason,updatedAt:$updatedAt}' >"$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$status_file"
}
finish() { local code=$?; if (( code == 0 )); then write_status success 0; else write_status failed "$code"; fi; }
trap finish EXIT
write_status running 0

set_dashboard_version() {
  local version=$1 dropin current
  dropin="${HOME}/.config/systemd/user/prime-dashboard-api.service.d"
  install -d -m 0755 "$dropin"
  current=$(sed -n 's/^Environment=PRIME_OPENSHELL_VERSION=//p' "$dropin/zz-openshell-version.conf" 2>/dev/null || true)
  if [[ "$current" != "$version" ]]; then
    printf '[Service]\nEnvironment=PRIME_OPENSHELL_VERSION=%s\n' "$version" >"$dropin/zz-openshell-version.conf"
    rm -f "$dropin/openshell-version.conf"
    systemctl --user daemon-reload
    systemctl --user restart prime-dashboard-api.service
  fi
}

exec 9>"${HOME}/.prime/agent/openshell-update.lock"
flock -n 9 || { failure_reason="Another OpenShell update is already running."; echo "$failure_reason" >&2; exit 75; }

test "$(dpkg --print-architecture)" = arm64
test -z "$(openshell --gateway spark-local sandbox list --all-workspaces --ids)" || {
  failure_reason="Update blocked: OpenShell sandboxes still exist. Finish work and delete them after preserving needed data, then retry."
  echo "$failure_reason" >&2
  exit 75
}

release=$(gh api repos/NVIDIA/OpenShell/releases/latest)
tag=$(jq -r .tag_name <<<"$release")
[[ $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]
version=${tag#v}
installed=$(openshell --version | awk '{print $NF}')
if ! dpkg --compare-versions "$version" gt "$installed"; then
  set_dashboard_version "$installed"
  echo "OpenShell ${installed} is already current."
  exit 0
fi
if dpkg --compare-versions "$installed" lt 0.1.0 && dpkg --compare-versions "$version" ge 0.1.0; then
  failure_reason="OpenShell ${installed} to ${version} is a breaking 0.0.x-to-0.1.x migration, not a one-click package update. Prime must migrate the gateway configuration, preserve gateway state, and approve its Docker volumes before installing 0.1.x. The current gateway is unchanged."
  echo "$failure_reason" >&2
  exit 75
fi
installer="${PRIME_WEBUI_REPO:-${HOME}/prime_agent_webui}/deploy/spark/openshell/install.sh"
pinned=$(sed -n 's/^version=\([0-9][0-9.]*\)$/\1/p' "$installer" 2>/dev/null || true)
if [[ $pinned != "$version" ]]; then
  failure_reason="OpenShell ${version} is upstream, but this Prime installation is pinned to ${pinned:-an unknown version}. Update and verify the Prime installer pin before upgrading."
  echo "$failure_reason" >&2
  exit 75
fi

asset=$(jq -r '.assets[].name | select(test("^openshell_[0-9.]+(-[0-9]+)?_arm64\\.deb$"))' <<<"$release")
test -n "$asset"
test "$(wc -l <<<"$asset")" -eq 1
staging=$(mktemp -d)
trap 'code=$?; rm -rf "$staging"; if (( code == 0 )); then write_status success 0; else write_status failed "$code"; fi' EXIT
gh release download "$tag" --repo NVIDIA/OpenShell --pattern "$asset" --pattern openshell-checksums-sha256.txt --dir "$staging"
checksum=$(grep -E "[[:space:]]${asset}$" "$staging/openshell-checksums-sha256.txt")
test -n "$checksum"
(cd "$staging" && printf '%s\n' "$checksum" | sha256sum --check --strict -)

sudo -n apt-get install -y "$staging/$asset"
systemctl --user restart openshell-gateway.service
openshell --gateway spark-local status
sudo -n -u prime-runner env HOME=/var/lib/prime-runner openshell --gateway spark-local status

set_dashboard_version "$version"
echo "OpenShell updated from ${installed} to ${version}."
