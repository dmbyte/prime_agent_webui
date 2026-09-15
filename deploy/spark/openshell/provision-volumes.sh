#!/usr/bin/env bash
set -euo pipefail

test "${EUID}" -ne 0 || { echo "Run as the Docker/WebUI owner, not root." >&2; exit 2; }

ensure_volume() {
  local name=$1 device=$2 legacy_device=${3:-} current
  test -d "$device" || { echo "Missing Prime storage directory: $device" >&2; exit 1; }
  if docker volume inspect "$name" >/dev/null 2>&1; then
    current=$(docker volume inspect "$name" --format '{{ index .Options "device" }}')
    if [[ "$current" != "$device" ]]; then
      if [[ -n "$legacy_device" && "$current" == "$legacy_device" ]]; then
        docker volume rm "$name" >/dev/null
      else
        echo "Volume $name points at unexpected storage: $current" >&2
        exit 1
      fi
    else
      return
    fi
  fi
  if ! docker volume inspect "$name" >/dev/null 2>&1; then
    docker volume create --driver local --opt type=none --opt o=bind --opt "device=$device" "$name" >/dev/null
  fi
}

workspace_root="${PRIME_RUNNER_WORKSPACE_ROOT:-${HOME}/prime-agent/tasks}"
install -d -m 0770 "${HOME}/prime-agent" "$workspace_root"
setfacl -m "u:prime-runner:rwx,g:prime-web:rwx,m::rwx,d:u:prime-runner:rwx,d:g:prime-web:rwx,d:m::rwx" "${HOME}/prime-agent" "$workspace_root"

ensure_workspace() {
  local owner=$1 target="$workspace_root/$owner"
  sudo install -d -o prime-runner -g prime-runner -m 0700 "$target"
  if [[ -d /var/lib/prime-runner/users/${owner}/workspace ]]; then
    sudo rsync -a --ignore-existing "/var/lib/prime-runner/users/${owner}/workspace/" "$target/"
  fi
  if [[ "$owner" == "$USER" && -d ${HOME}/prime-dgx-agent ]]; then
    sudo rsync -a --ignore-existing --exclude uploads "${HOME}/prime-dgx-agent/" "$target/"
  fi
  sudo chown -R prime-runner:prime-runner "$target"
  sudo setfacl -m "u:${USER}:rwx,d:u:${USER}:rwx,g:prime-web:rwx,d:g:prime-web:rwx,m::rwx,d:m::rwx,o::---,d:o::---" "$target"
  printf '%s' "$target"
}

for root in /mnt /media /srv /opt; do
  ensure_volume "prime-shared-${root#/}" "$root"
done

while IFS= read -r owner; do
  [[ $owner =~ ^[A-Za-z0-9_.-]{2,32}$ ]] || { echo "Unsafe Prime owner directory: $owner" >&2; exit 1; }
  owner_workspace=$(ensure_workspace "$owner")
  ensure_volume "prime-${owner}-prime" "/var/lib/prime-runner/users/${owner}/prime"
  ensure_volume "prime-${owner}-workspace" "$owner_workspace" "/var/lib/prime-runner/users/${owner}/workspace"
  for mode in restricted internet lan full; do
    ensure_volume "prime-${owner}-gateway-${mode}" "/var/lib/prime-runner/gateway/${owner}/${mode}"
  done
done < <(sudo find /var/lib/prime-runner/users -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
