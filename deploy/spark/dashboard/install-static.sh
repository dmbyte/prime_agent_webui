#!/usr/bin/env bash
set -euo pipefail
source_dir=${1:-"${HOME}/prime-dgx-dashboard"}
web_root=/var/www/prime-agent
sudo install -d -o root -g root -m 0755 "$web_root" "$web_root/assets"
sudo install -o root -g root -m 0644 "$source_dir/index.html" "$source_dir/login.html" "$web_root/"
sudo install -o root -g root -m 0644 \
  "$source_dir/app-v2.js" "$source_dir/app-v2.css" \
  "$source_dir/enhancements.css" "$source_dir/login.js" \
  "$source_dir/login.css" "$web_root/assets/"
