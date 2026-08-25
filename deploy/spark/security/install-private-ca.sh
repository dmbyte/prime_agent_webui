#!/usr/bin/env bash
set -euo pipefail
ca_dir=/etc/nginx/prime-agent-ca
tls_dir=/etc/nginx/prime-agent-tls
public_ca=/var/www/prime-agent/prime-webui-ca.crt
sudo install -d -o root -g root -m 0700 "$ca_dir"
sudo install -d -o root -g root -m 0700 "$tls_dir"
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
if [[ ! -f "$ca_dir/ca.key" ]]; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$tmp_dir/ca.key"
  openssl req -x509 -new -sha256 -days 3650 -key "$tmp_dir/ca.key" -out "$tmp_dir/ca.crt" -subj "/CN=DGX Spark Prime Private CA/O=Private LAN"
  sudo install -o root -g root -m 0600 "$tmp_dir/ca.key" "$ca_dir/ca.key"
  sudo install -o root -g root -m 0644 "$tmp_dir/ca.crt" "$ca_dir/ca.crt"
fi
cat >"$tmp_dir/san.cnf" <<'EOF'
[req]
distinguished_name=dn
req_extensions=req_ext
prompt=no
[dn]
CN=spark-c562
O=Private LAN
[req_ext]
subjectAltName=@alt_names
[alt_names]
DNS.1=spark-c562
DNS.2=localhost
IP.1=172.16.253.231
IP.2=127.0.0.1
EOF
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$tmp_dir/server.key"
openssl req -new -key "$tmp_dir/server.key" -out "$tmp_dir/server.csr" -config "$tmp_dir/san.cnf"
sudo openssl x509 -req -sha256 -days 825 -in "$tmp_dir/server.csr" -CA "$ca_dir/ca.crt" -CAkey "$ca_dir/ca.key" -CAcreateserial -out "$tmp_dir/server.crt" -extensions req_ext -extfile "$tmp_dir/san.cnf"
sudo install -o root -g root -m 0600 "$tmp_dir/server.key" "$tls_dir/prime-agent.key"
sudo install -o root -g root -m 0644 "$tmp_dir/server.crt" "$tls_dir/prime-agent.crt"
sudo install -o root -g root -m 0644 "$ca_dir/ca.crt" "$public_ca"
sudo nginx -t
sudo systemctl reload nginx
echo "Install $public_ca on each LAN/VPN client to trust Prime WebUI."
