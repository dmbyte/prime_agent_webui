#!/usr/bin/env bash
set -euo pipefail

test "${EUID}" -ne 0 || { echo "Run as the Docker/WebUI owner, not root." >&2; exit 2; }

ensure_volume() {
  local name=$1 device=$2 current
  test -d "$device" || { echo "Missing Prime storage directory: $device" >&2; exit 1; }
  if docker volume inspect "$name" >/dev/null 2>&1; then
    current=$(docker volume inspect "$name" --format '{{ index .Options "device" }}')
    test "$current" = "$device" || { echo "Volume $name points at unexpected storage: $current" >&2; exit 1; }
  else
    docker volume create --driver local --opt type=none --opt o=bind --opt "device=$device" "$name" >/dev/null
  fi
}

for root in /mnt /media /srv /opt; do
  ensure_volume "prime-shared-${root#/}" "$root"
done

while IFS= read -r owner; do
  [[ $owner =~ ^[A-Za-z0-9_.-]{2,32}$ ]] || { echo "Unsafe Prime owner directory: $owner" >&2; exit 1; }
  ensure_volume "prime-${owner}-prime" "/var/lib/prime-runner/users/${owner}/prime"
  ensure_volume "prime-${owner}-workspace" "/var/lib/prime-runner/users/${owner}/workspace"
  for mode in restricted internet lan full; do
    ensure_volume "prime-${owner}-gateway-${mode}" "/var/lib/prime-runner/gateway/${owner}/${mode}"
  done
done < <(sudo find /var/lib/prime-runner/users -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
