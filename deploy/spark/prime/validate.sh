#!/usr/bin/env bash
set -euo pipefail

fail=0
for endpoint in 30000 30001; do
  if ! curl --fail --silent --max-time 10 "http://127.0.0.1:${endpoint}/v1/models" >/dev/null; then
    echo "FAIL: model endpoint ${endpoint}" >&2
    fail=1
  fi
done

if ! curl --fail --silent --max-time 10 http://127.0.0.1:7681/terminal/ >/dev/null; then
  echo "FAIL: private Prime browser interface" >&2
  fail=1
fi

auth_status="$(curl --insecure --silent --output /dev/null --write-out '%{http_code}' --max-time 10 https://127.0.0.1:8443/)"
if [[ "${auth_status}" != "302" ]]; then
  echo "FAIL: authenticated HTTPS endpoint returned ${auth_status}, expected login redirect without a session" >&2
  fail=1
fi

lan_auth_status="$(curl --insecure --silent --output /dev/null --write-out '%{http_code}' --max-time 10 https://172.16.253.231:8443/)"
if [[ "${lan_auth_status}" != "302" ]]; then
  echo "FAIL: LAN session endpoint returned ${lan_auth_status}, expected login redirect without a session" >&2
  fail=1
fi

if ss -ltn | awk '$4 ~ /(^|:)(3000[01]|7681)$/ && $4 !~ /^127\.0\.0\.1:/ {exit 1}'; then
  :
else
  echo "FAIL: a model endpoint is not loopback-only" >&2
  fail=1
fi

if ss -ltn | awk '$4 ~ /(^|:)(8764|8765|8787)$/ && $4 !~ /^127\.0\.0\.1:/ {exit 1}'; then
  :
else
  echo "FAIL: a dashboard service is not loopback-only" >&2
  fail=1
fi

broker_status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 10 http://127.0.0.1:8764/auth/check)"
if [[ "${broker_status}" != "401" ]]; then
  echo "FAIL: session broker returned ${broker_status}, expected 401 without a session" >&2
  fail=1
fi

if ss -ltn | awk '$4 ~ /(^|:)(80)$/ {exit 1}'; then
  :
else
  echo "FAIL: an unnecessary plaintext HTTP listener is active" >&2
  fail=1
fi

security_headers="$(curl --insecure --silent --head --max-time 10 https://127.0.0.1:8443/)"
for header in content-security-policy x-content-type-options referrer-policy permissions-policy; do
  if ! grep --ignore-case --quiet "^${header}:" <<<"${security_headers}"; then
    echo "FAIL: authenticated HTTPS endpoint is missing ${header}" >&2
    fail=1
  fi
done

total_kib="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
available_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
minimum_available_kib=$(( total_kib / 5 ))
if (( available_kib < minimum_available_kib )); then
  echo "FAIL: less than 20% system memory available" >&2
  fail=1
fi

if (( fail != 0 )); then exit 1; fi
echo "PASS: both local models healthy, private, and memory headroom >= 20%"
