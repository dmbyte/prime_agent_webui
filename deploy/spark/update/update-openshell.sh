#!/usr/bin/env bash
set -euo pipefail

status_dir="${HOME}/.prime/agent/update-status"
status_file="$status_dir/openshell.json"
failure_reason=""
phase="initializing the update"
write_status() {
  local result=$1 exit_code=$2 temporary
  if [[ $result == failed && -z $failure_reason ]]; then
    failure_reason="OpenShell update failed while ${phase} (exit ${exit_code}). Check the update service log."
  fi
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

verify_gateway() {
  local attempt
  phase="waiting for the gateway and both client identities"
  # systemctl restart returns before the gateway binds its listening socket.
  for attempt in {1..30}; do
    if timeout 5s openshell --gateway spark-local status >/dev/null 2>&1 &&
       timeout 5s sudo -n -u prime-runner env HOME=/var/lib/prime-runner openshell --gateway spark-local status >/dev/null 2>&1; then
      openshell --gateway spark-local status
      return 0
    fi
    sleep 2
  done
  failure_reason="OpenShell is installed, but the gateway did not become ready for both WebUI and task-runner clients. Check openshell-gateway.service before starting work."
  return 1
}

exec 9>"${HOME}/.prime/agent/openshell-update.lock"
flock -n 9 || { failure_reason="Another OpenShell update is already running."; echo "$failure_reason" >&2; exit 75; }

test "$(dpkg --print-architecture)" = arm64
# A running unit can still be binding its listener after package maintenance.
# Check readiness before the first sandbox query, not just after our restart.
verify_gateway
phase="checking for active sandboxes"
sandbox_ids=$(openshell --gateway spark-local sandbox list --all-workspaces --ids)
test -z "$sandbox_ids" || {
  failure_reason="Update blocked: OpenShell sandboxes still exist. Finish work and delete them after preserving needed data, then retry."
  echo "$failure_reason" >&2
  exit 75
}

phase="checking the upstream release"
release=$(gh api repos/NVIDIA/OpenShell/releases/latest)
tag=$(jq -r .tag_name <<<"$release")
[[ $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]
version=${tag#v}
installed=$(openshell --version | awk '{print $NF}')
if ! dpkg --compare-versions "$version" gt "$installed"; then
  verify_gateway
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
pinned_sha=$(sed -n 's/^deb_sha256=\([a-f0-9]\{64\}\)$/\1/p' "$installer" 2>/dev/null || true)
if [[ $pinned != "$version" ]]; then
  failure_reason="OpenShell ${version} is upstream, but this Prime installation is pinned to ${pinned:-an unknown version}. Update and verify the Prime installer pin before upgrading."
  echo "$failure_reason" >&2
  exit 75
fi
[[ $pinned_sha =~ ^[a-f0-9]{64}$ ]] || {
  failure_reason="The reviewed OpenShell package checksum is missing from the Prime installer."
  exit 75
}

phase="selecting the ARM64 package"
asset=$(jq -r '.assets[].name | select(test("^openshell_[0-9.]+(-[0-9]+)?_arm64\\.deb$"))' <<<"$release")
test -n "$asset"
test "$(wc -l <<<"$asset")" -eq 1
staging=$(mktemp -d)
trap 'code=$?; rm -rf "$staging"; if (( code == 0 )); then write_status success 0; else write_status failed "$code"; fi' EXIT
phase="downloading and verifying the reviewed package"
gh release download "$tag" --repo NVIDIA/OpenShell --pattern "$asset" --pattern openshell-checksums-sha256.txt --dir "$staging"
checksum=$(grep -E "[[:space:]]${asset}$" "$staging/openshell-checksums-sha256.txt")
test -n "$checksum"
(cd "$staging" && printf '%s\n' "$checksum" | sha256sum --check --strict -)
(cd "$staging" && printf '%s  %s\n' "$pinned_sha" "$asset" | sha256sum --check --strict -)

phase="validating the existing gateway configuration with the new package"
dpkg-deb -x "$staging/$asset" "$staging/extracted"
OPENSHELL_GATEWAY_CONFIG="${HOME}/.config/openshell/gateway.toml" "$staging/extracted/usr/bin/openshell-gateway" config preflight

# Work may have started during the download; never knowingly disrupt it.
phase="rechecking for active sandboxes"
sandbox_ids=$(openshell --gateway spark-local sandbox list --all-workspaces --ids)
test -z "$sandbox_ids" || {
  failure_reason="Update deferred: an OpenShell sandbox started during preparation. Finish its work before retrying."
  exit 75
}

phase="installing the verified package"
sudo -n apt-get install -y "$staging/$asset"
phase="restarting and checking the gateway"
systemctl --user daemon-reload
systemctl --user restart openshell-gateway.service
verify_gateway

set_dashboard_version "$version"
echo "OpenShell updated from ${installed} to ${version}."
