#!/usr/bin/env bash
set -euo pipefail

webui_version="0.3.0"
prime_version="0.8.0"
port=8443
bind_address=""
server_name=""
install_packages=1
install_prime=1
set_password=1

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Install Prime WebUI for the current non-root user.

  --bind-address ADDRESS  Private LAN/VPN address for Nginx (auto-detected)
  --server-name NAME      DNS name placed in the private TLS certificate
  --port PORT             HTTPS port (default: 8443)
  --skip-packages         Do not install OS packages
  --skip-prime            Require an existing prime-agent installation
  --skip-password         Do not prompt for the initial WebUI password
  -h, --help              Show this help

The installer does not open a public firewall or enable preview container mode.
EOF
}

while (($#)); do
  case "$1" in
    --bind-address) bind_address=${2:?missing address}; shift 2 ;;
    --server-name) server_name=${2:?missing name}; shift 2 ;;
    --port) port=${2:?missing port}; shift 2 ;;
    --skip-packages) install_packages=0; shift ;;
    --skip-prime) install_prime=0; shift ;;
    --skip-password) set_password=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ $EUID -eq 0 ]]; then
  echo "Run this installer as the account that will own Prime WebUI, not as root." >&2
  exit 2
fi
[[ $port =~ ^[0-9]+$ ]] && ((port >= 1024 && port <= 65535)) || {
  echo "Port must be between 1024 and 65535." >&2; exit 2;
}
command -v sudo >/dev/null || { echo "sudo is required for packages, Nginx, and TLS." >&2; exit 2; }
sudo -v

source /etc/os-release
family=""
case " ${ID:-} ${ID_LIKE:-} " in
  *ubuntu*|*debian*) family=debian ;;
  *rhel*|*fedora*|*centos*|*rocky*|*almalinux*) family=redhat ;;
  *sles*|*suse*) family=suse ;;
  *) echo "Unsupported distribution family: ${PRETTY_NAME:-unknown}. Use --skip-packages after installing the README prerequisites." >&2; exit 2 ;;
esac

if ((install_packages)); then
  case "$family" in
    debian)
      sudo apt-get update
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx openssl python3 curl git
      ;;
    redhat)
      manager=dnf; command -v dnf >/dev/null || manager=yum
      sudo "$manager" install -y nginx openssl python3 curl git policycoreutils-python-utils
      ;;
    suse)
      sudo zypper --non-interactive install nginx openssl python3 curl git
      ;;
  esac
fi

for command_name in nginx openssl python3 curl git systemctl; do
  command -v "$command_name" >/dev/null || { echo "Missing required command: $command_name" >&2; exit 2; }
done

if ((install_prime)); then
  installer=$(mktemp)
  trap 'rm -f "$installer"' EXIT
  curl -fsSL https://app.primeintellect.ai/prime-agent/install.sh -o "$installer"
  sh "$installer" "$prime_version"
  rm -f "$installer"
  trap - EXIT
fi

prime_bin="${HOME}/.local/share/prime-agent-node/current/bin/prime-agent"
[[ -x $prime_bin ]] || { echo "Prime Agent is not installed at $prime_bin" >&2; exit 2; }

if [[ -z $bind_address ]]; then
  bind_address=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
[[ $bind_address =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || {
  echo "Could not determine a safe bind address; pass --bind-address explicitly." >&2; exit 2;
}
python3 - "$bind_address" <<'PY'
import ipaddress, sys
value = ipaddress.ip_address(sys.argv[1])
if value.version != 4 or value.is_unspecified or value.is_multicast:
    raise SystemExit("Bind address must be a specific unicast IPv4 address")
PY
server_name=${server_name:-$(hostname -f 2>/dev/null || hostname)}
[[ $server_name =~ ^[A-Za-z0-9.-]+$ ]] || { echo "Invalid server name." >&2; exit 2; }

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
[[ $repo_dir != *'"'* && $repo_dir != *$'\n'* ]] || { echo "Repository path contains unsupported characters." >&2; exit 2; }
dashboard="${HOME}/prime-dgx-dashboard"
workspace="${HOME}/prime-dgx-agent"
unit_dir="${HOME}/.config/systemd/user"
update_dir="${HOME}/prime-update"
install -d -m 0700 "$dashboard" "$workspace" "$workspace/uploads" "${HOME}/.prime/agent" "${HOME}/.config/prime-agent"
install -d -m 0755 "$unit_dir" "$update_dir" "${HOME}/.local/bin"
install -m 0644 "$repo_dir"/deploy/spark/dashboard/*.py "$repo_dir"/deploy/spark/dashboard/*.js "$repo_dir"/deploy/spark/dashboard/*.css "$repo_dir"/deploy/spark/dashboard/*.html "$dashboard"/
install -m 0755 "$repo_dir/deploy/spark/dashboard/install-static.sh" "$dashboard/install-static.sh"
install -m 0755 "$repo_dir/deploy/spark/update/"*.sh "$update_dir"/
install -m 0755 "$repo_dir/deploy/spark/dashboard/set_web_password.py" "${HOME}/.local/bin/prime-web-password"

cat >"$unit_dir/prime-auth.service" <<EOF
[Unit]
Description=Prime WebUI local session broker
After=network.target

[Service]
Type=simple
Environment=PRIME_AUTH_USER=${USER}
Environment=PRIME_AUTH_CREDENTIAL=${HOME}/.config/prime-agent/web-auth.json
ExecStart=/usr/bin/python3 ${dashboard}/auth.py
Restart=on-failure
RestartSec=3
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${HOME}/.config/prime-agent
UMask=0077
NoNewPrivileges=yes

[Install]
WantedBy=default.target
EOF

origins="https://${bind_address}:${port},https://${server_name}:${port},https://127.0.0.1:${port},https://localhost:${port}"
cat >"$unit_dir/prime-dashboard-api.service" <<EOF
[Unit]
Description=Prime WebUI API
After=network.target

[Service]
Type=simple
Environment=PRIME_WEB_ORIGINS=${origins}
Environment="PRIME_WEBUI_REPO=${repo_dir}"
Environment=PRIME_INITIAL_ADMIN=${USER}
ExecStart=/usr/bin/python3 ${dashboard}/api_v2.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${HOME}/.prime/agent ${workspace}
UMask=0077

[Install]
WantedBy=default.target
EOF

for update_unit in prime-update-agent.service prime-update-webui.service; do
  install -m 0644 "$repo_dir/deploy/spark/systemd/$update_unit" "$unit_dir/$update_unit"
done
cat >>"$unit_dir/prime-update-webui.service" <<EOF
Environment="PRIME_WEBUI_REPO=${repo_dir}"
EOF

"$dashboard/install-static.sh" "$dashboard"
sudo sed -i 's/<button id="openConsole">/<button id="openConsole" hidden>/' /var/www/prime-agent/index.html

tls_dir=/etc/nginx/prime-agent-tls
ca_dir=/etc/nginx/prime-agent-ca
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
sudo install -d -o root -g root -m 0700 "$tls_dir" "$ca_dir"
if [[ ! -f $ca_dir/ca.key ]]; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$temporary/ca.key"
  openssl req -x509 -new -sha256 -days 3650 -key "$temporary/ca.key" -out "$temporary/ca.crt" -subj "/CN=Prime WebUI Private CA/O=Private LAN"
  sudo install -o root -g root -m 0600 "$temporary/ca.key" "$ca_dir/ca.key"
  sudo install -o root -g root -m 0644 "$temporary/ca.crt" "$ca_dir/ca.crt"
fi
cat >"$temporary/san.cnf" <<EOF
[req]
distinguished_name=dn
req_extensions=req_ext
prompt=no
[dn]
CN=${server_name}
O=Private LAN
[req_ext]
subjectAltName=@alt_names
[alt_names]
DNS.1=${server_name}
DNS.2=localhost
IP.1=${bind_address}
IP.2=127.0.0.1
EOF
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$temporary/server.key"
openssl req -new -key "$temporary/server.key" -out "$temporary/server.csr" -config "$temporary/san.cnf"
sudo openssl x509 -req -sha256 -days 825 -in "$temporary/server.csr" -CA "$ca_dir/ca.crt" -CAkey "$ca_dir/ca.key" -CAcreateserial -out "$temporary/server.crt" -extensions req_ext -extfile "$temporary/san.cnf"
sudo install -o root -g root -m 0600 "$temporary/server.key" "$tls_dir/prime-agent.key"
sudo install -o root -g root -m 0644 "$temporary/server.crt" "$tls_dir/prime-agent.crt"
sudo install -o root -g root -m 0644 "$ca_dir/ca.crt" /var/www/prime-agent/prime-webui-ca.crt

nginx_conf="$temporary/prime-agent.conf"
sed \
  -e "s/172\\.16\\.253\\.231/${bind_address//./\\.}/g" \
  -e "s/spark-c562/${server_name}/g" \
  -e "s/:8443/:${port}/g" \
  "$repo_dir/deploy/spark/nginx/prime-agent.conf" >"$nginx_conf"
sudo install -o root -g root -m 0644 "$repo_dir/deploy/spark/nginx/prime-security.conf" /etc/nginx/conf.d/prime-security.conf
sudo install -o root -g root -m 0644 "$nginx_conf" /etc/nginx/conf.d/prime-agent.conf
sudo nginx -t
if [[ $family == redhat ]] && command -v getenforce >/dev/null && [[ $(getenforce) == Enforcing ]]; then
  sudo setsebool -P httpd_can_network_connect 1
fi
sudo systemctl enable --now nginx
sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now prime-auth.service prime-dashboard-api.service

if ((set_password)); then
  PRIME_AUTH_USER="$USER" "${HOME}/.local/bin/prime-web-password"
  systemctl --user restart prime-auth.service
fi

curl -fsS http://127.0.0.1:8765/api/telemetry >/dev/null
code=$(curl -ksS -o /dev/null -w '%{http_code}' "https://127.0.0.1:${port}/api/state")
[[ $code == 401 ]] || { echo "Expected unauthenticated API status 401, received $code" >&2; exit 1; }
if ! command -v gh >/dev/null; then
  echo "Note: install and authenticate GitHub CLI (gh) to enable in-app release checks and updates." >&2
fi

cat <<EOF

Prime WebUI ${webui_version} is installed.

Open: https://${bind_address}:${port}/
CA certificate: https://${bind_address}:${port}/prime-webui-ca.crt

The firewall was not changed. If clients cannot connect, allow TCP ${port} only
from your private LAN/VPN using the distribution-specific examples in README.md.
Configure a provider from Settings → Add provider or run Prime Agent and use /login.
EOF
