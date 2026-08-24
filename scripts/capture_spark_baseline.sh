#!/usr/bin/env bash
set -Eeuo pipefail

baseline_id="dgx-spark-baseline-20260823T154649-0500"
baseline_dir="/var/backups/${baseline_id}"

sudo -n install -d -m 0700 -o root -g root "${baseline_dir}"

sudo -n bash -c "date --iso-8601=seconds > '${baseline_dir}/captured_at.txt'"
sudo -n bash -c "hostnamectl > '${baseline_dir}/hostnamectl.txt'"
sudo -n bash -c "uname -a > '${baseline_dir}/uname.txt'"
sudo -n bash -c "cat /proc/cmdline > '${baseline_dir}/kernel-command-line.txt'"
sudo -n bash -c "lscpu > '${baseline_dir}/lscpu.txt'"
sudo -n bash -c "free -h > '${baseline_dir}/memory.txt'"
sudo -n bash -c "lsblk -e7 -o NAME,PATH,SIZE,TYPE,FSTYPE,FSVER,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL > '${baseline_dir}/block-devices.txt'"
sudo -n bash -c "findmnt --real -o TARGET,SOURCE,FSTYPE,OPTIONS > '${baseline_dir}/mounts.txt'"
sudo -n bash -c "swapon --show --output NAME,TYPE,SIZE,USED,PRIO,UUID,LABEL > '${baseline_dir}/swap.txt'"
sudo -n bash -c "nvidia-smi -q > '${baseline_dir}/nvidia-smi-q.txt'"
sudo -n bash -c "fwupdmgr get-devices > '${baseline_dir}/firmware-devices.txt' 2>&1 || true"
sudo -n bash -c "nvme smart-log /dev/nvme0 > '${baseline_dir}/nvme-smart.txt' 2>&1 || true"
sudo -n bash -c "ip -details address > '${baseline_dir}/ip-addresses.txt'"
sudo -n bash -c "ip route show table all > '${baseline_dir}/ip-routes.txt'"
sudo -n bash -c "resolvectl status > '${baseline_dir}/dns.txt' 2>&1 || true"
sudo -n bash -c "ss -lntup > '${baseline_dir}/listening-sockets.txt' 2>&1 || true"
sudo -n bash -c "nft list ruleset > '${baseline_dir}/nft-ruleset.txt' 2>&1 || true"
sudo -n bash -c "ufw status verbose > '${baseline_dir}/ufw-status.txt' 2>&1 || true"
sudo -n bash -c "systemctl list-unit-files --no-pager > '${baseline_dir}/systemd-unit-files.txt'"
sudo -n bash -c "systemctl list-units --all --no-pager > '${baseline_dir}/systemd-units.txt'"
sudo -n bash -c "systemctl list-timers --all --no-pager > '${baseline_dir}/systemd-timers.txt'"
sudo -n bash -c "systemctl --failed --no-pager > '${baseline_dir}/systemd-failed.txt'"
sudo -n bash -c "dpkg-query -W -f='\${Package}\t\${Version}\t\${Architecture}\n' | sort > '${baseline_dir}/dpkg-manifest.tsv'"
sudo -n bash -c "apt-mark showmanual | sort > '${baseline_dir}/apt-manual.txt'"
sudo -n bash -c "snap list > '${baseline_dir}/snap-manifest.txt' 2>&1 || true"
sudo -n bash -c "python3 -m pip freeze | sort > '${baseline_dir}/python-system-freeze.txt' 2>&1 || true"
sudo -n bash -c "docker version > '${baseline_dir}/docker-version.txt' 2>&1 || true"
sudo -n bash -c "docker ps -a --no-trunc > '${baseline_dir}/docker-containers.txt' 2>&1 || true"
sudo -n bash -c "docker images --digests --no-trunc > '${baseline_dir}/docker-images.txt' 2>&1 || true"
sudo -n bash -c "docker volume ls > '${baseline_dir}/docker-volumes.txt' 2>&1 || true"
sudo -n bash -c "docker network ls > '${baseline_dir}/docker-networks.txt' 2>&1 || true"
sudo -n bash -c "docker inspect --format '{{.Name}} image={{.Config.Image}} image_id={{.Image}} command={{json .Config.Cmd}} restart={{.HostConfig.RestartPolicy.Name}} network={{.HostConfig.NetworkMode}} ipc={{.HostConfig.IpcMode}} shm={{.HostConfig.ShmSize}} mounts={{range .Mounts}}{{.Type}}:{{.Source}}:{{.Destination}}:rw={{.RW}};{{end}} ports={{json .NetworkSettings.Ports}}' \$(docker ps -aq) > '${baseline_dir}/docker-inspect-sanitized.txt' 2>&1 || true"

sudo -n tar --ignore-failed-read --numeric-owner -czf "${baseline_dir}/configuration.tar.gz" \
  /etc/apt /etc/default /etc/docker /etc/fstab /etc/hosts /etc/hostname \
  /etc/modules /etc/modprobe.d /etc/netplan /etc/NetworkManager/system-connections \
  /etc/nginx /etc/nsswitch.conf /etc/resolv.conf /etc/security /etc/ssh/sshd_config \
  /etc/ssh/sshd_config.d /etc/sudoers /etc/sudoers.d /etc/sysctl.conf /etc/sysctl.d \
  /etc/systemd/system /etc/ufw /etc/docker/daemon.json \
  /home/dbyte/vllm-nemotron35 /home/dbyte/.hermes/config.yaml \
  /home/dbyte/.hermes/SOUL.md /home/dbyte/.hermes/active_profile \
  /home/dbyte/.hermes/.env /home/dbyte/.hermes/auth.json \
  /home/dbyte/.hermes/webui.env /home/dbyte/.hermes/webui/settings.json \
  /home/dbyte/.hermes/hermes-webui /home/dbyte/.hermes/hermes-agent \
  2> >(sudo -n tee "${baseline_dir}/archive-warnings.txt" >/dev/null)

sudo -n bash -c "find '${baseline_dir}' -maxdepth 1 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > '${baseline_dir}/SHA256SUMS'"
sudo -n chmod -R go-rwx "${baseline_dir}"

sudo -n du -sh "${baseline_dir}"
sudo -n sha256sum "${baseline_dir}/configuration.tar.gz"
sudo -n sha256sum -c "${baseline_dir}/SHA256SUMS"
