#!/usr/bin/env bash
set -euo pipefail

status_dir="${HOME}/.prime/agent/update-status"
status_file="$status_dir/openshell.json"
failure_reason=""
phase="initializing the update"
gateway_stopped=false
staging=""
install -d -m 0700 "${HOME}/.prime/agent"
exec 9>"${HOME}/.prime/agent/openshell-update.lock"
flock -n 9 || { echo 'Another OpenShell update is already running.' >&2; exit 75; }
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
finish() {
  local code=$?
  if "$gateway_stopped"; then systemctl --user start openshell-gateway.service || true; fi
  if [[ -n "$staging" ]]; then rm -rf "$staging"; fi
  if (( code == 0 )); then write_status success 0; else write_status failed "$code"; fi
}
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

phase="blocking new work for maintenance"
# Never create/replace this root-provisioned inode: every producer locks it.
exec 8</var/lib/prime-runner/openshell-maintenance.lock
flock -n -x 8 || { failure_reason="Update deferred: a task or connection is starting/running. Finish it and retry."; exit 75; }

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
  python3 "${HOME}/prime-update/verify-openshell.py" --version "$installed"
  set_dashboard_version "$installed"
  echo "OpenShell ${installed} is already current."
  exit 0
fi
if dpkg --compare-versions "$installed" lt 0.1.0 && dpkg --compare-versions "$version" ge 0.1.0; then
  failure_reason="OpenShell ${installed} to ${version} is a breaking 0.0.x-to-0.1.x migration, not a one-click package update. Prime must migrate the gateway configuration, preserve gateway state, and approve its Docker volumes before installing 0.1.x. The current gateway is unchanged."
  echo "$failure_reason" >&2
  exit 75
fi
approval="${HOME}/prime-update/openshell-release.json"
pinned=$(jq -er .version "$approval")
pinned_sha=$(jq -er .sha256 "$approval")
if [[ $pinned != "$version" ]]; then
  failure_reason="OpenShell ${version} is upstream, but this Prime installation is pinned to ${pinned:-an unknown version}. Install the reviewed Prime approval manifest before upgrading."
  echo "$failure_reason" >&2
  exit 75
fi
[[ $pinned_sha =~ ^[a-f0-9]{64}$ ]] || {
  failure_reason="The reviewed OpenShell package checksum is missing from the installed approval manifest."
  exit 75
}

phase="selecting the ARM64 package"
asset=$(jq -r '.assets[].name | select(test("^openshell_[0-9.]+(-[0-9]+)?_arm64\\.deb$"))' <<<"$release")
test -n "$asset"
test "$(wc -l <<<"$asset")" -eq 1
test "$asset" = "$(jq -er .asset "$approval")"
staging=$(mktemp -d)
phase="downloading and verifying the reviewed package"
gh release download "$tag" --repo NVIDIA/OpenShell --pattern "$asset" --pattern openshell-checksums-sha256.txt --dir "$staging"
checksum=$(awk -v asset="$asset" '$2 == asset {print}' "$staging/openshell-checksums-sha256.txt")
test -n "$checksum"
test "$(wc -l <<<"$checksum")" -eq 1
(cd "$staging" && printf '%s\n' "$checksum" | sha256sum --check --strict -)
(cd "$staging" && printf '%s  %s\n' "$pinned_sha" "$asset" | sha256sum --check --strict -)

phase="validating the existing gateway configuration with the new package"
dpkg-deb -x "$staging/$asset" "$staging/extracted"
OPENSHELL_LOCAL_TLS_DIR="${HOME}/.local/state/openshell/tls" OPENSHELL_GATEWAY_CONFIG="${HOME}/.config/openshell/gateway.toml" "$staging/extracted/usr/bin/openshell-gateway" config preflight

phase="preparing matching supervisor and sandbox runtimes"
for component in supervisor sandbox; do
  docker pull "ghcr.io/nvidia/openshell/${component}:${version}"
done

phase="preserving rollback package and gateway state"
backup=$(mktemp -d "${HOME}/.prime/agent/openshell-backup.XXXXXX")
chmod 0700 "$backup"
old_asset="openshell_${installed}-1_arm64.deb"
gh release download "v${installed}" --repo NVIDIA/OpenShell --pattern "$old_asset" --pattern openshell-checksums-sha256.txt --dir "$backup"
old_checksum=$(awk -v asset="$old_asset" '$2 == asset {print}' "$backup/openshell-checksums-sha256.txt")
test -n "$old_checksum" && test "$(wc -l <<<"$old_checksum")" -eq 1
(cd "$backup" && printf '%s\n' "$old_checksum" | sha256sum --check --strict -)
cp -a "$approval" "$backup/reviewed-target.json"
docker image inspect "ghcr.io/nvidia/openshell/supervisor:${version}" "ghcr.io/nvidia/openshell/sandbox:${version}" >"$backup/runtime-images.json"

# Work may have started during the download; never knowingly disrupt it.
phase="rechecking for active sandboxes"
sandbox_ids=$(openshell --gateway spark-local sandbox list --all-workspaces --ids)
test -z "$sandbox_ids" || {
  failure_reason="Update deferred: an OpenShell sandbox started during preparation. Finish its work before retrying."
  exit 75
}

phase="installing the verified package"
# Quiesce before copying SQLite/state; the exclusive admission lease remains held.
systemctl --user stop openshell-gateway.service
gateway_stopped=true
if ! tar -C "$HOME" -czf "$backup/gateway-state.tgz" .config/openshell .local/state/openshell; then
  systemctl --user start openshell-gateway.service
  exit 1
fi
chmod 0600 "$backup"/*
sudo -n apt-get install -y "$staging/$asset"
phase="restarting and checking the gateway"
systemctl --user daemon-reload
systemctl --user restart openshell-gateway.service
verify_gateway
gateway_stopped=false
phase="testing fresh sandbox execution, streaming and cleanup"
python3 "${HOME}/prime-update/verify-openshell.py" --version "$version"

set_dashboard_version "$version"
echo "OpenShell updated from ${installed} to ${version}."
