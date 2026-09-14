#!/usr/bin/env bash
set -euo pipefail

status_dir="${HOME}/.prime/agent/update-status"
status_file="$status_dir/openshell.json"
write_status() {
  local result=$1 exit_code=$2 temporary
  install -d -m 0700 "$status_dir"
  temporary=$(mktemp "$status_dir/.openshell.XXXXXX")
  printf '{"ran":true,"result":"%s","exitCode":%d,"updatedAt":"%s"}\n' "$result" "$exit_code" "$(date --utc +%FT%TZ)" >"$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$status_file"
}
finish() { local code=$?; if (( code == 0 )); then write_status success 0; else write_status failed "$code"; fi; }
trap finish EXIT
write_status running 0

exec 9>"${HOME}/.prime/agent/openshell-update.lock"
flock -n 9 || { echo "Another OpenShell update is already running." >&2; exit 75; }

test "$(dpkg --print-architecture)" = arm64
test -z "$(openshell --gateway spark-local sandbox list --all-workspaces --ids)" || {
  echo "OpenShell cannot be updated while sandboxes exist." >&2
  exit 75
}

release=$(gh api repos/NVIDIA/OpenShell/releases/latest)
tag=$(jq -r .tag_name <<<"$release")
[[ $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]
version=${tag#v}
installed=$(openshell --version | awk '{print $NF}')
if ! dpkg --compare-versions "$version" gt "$installed"; then
  echo "OpenShell ${installed} is already current."
  exit 0
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

dropin="${HOME}/.config/systemd/user/prime-dashboard-api.service.d"
install -d -m 0755 "$dropin"
printf '[Service]\nEnvironment=PRIME_OPENSHELL_VERSION=%s\n' "$version" >"$dropin/openshell-version.conf"
systemctl --user daemon-reload
systemctl --user restart prime-dashboard-api.service
echo "OpenShell updated from ${installed} to ${version}."
