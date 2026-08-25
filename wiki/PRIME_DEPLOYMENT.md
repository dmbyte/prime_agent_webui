# Prime Agent deployment on DGX Spark

Last verified: 2026-08-24

## Service layout

| Component | Runtime location | Verified state |
|---|---|---|
| Prime Agent 0.8.0 | `~/.local/share/prime-agent-node/` | `prime-dgx` default-route test passed |
| Nemotron + DSpark | `vllm-nemotron35.service`, 127.0.0.1:30000 | enabled, active, text test passed |
| Qwen 3.6 NVFP4 | `vllm-qwen36.service`, 127.0.0.1:30001 | enabled, active, text and image tests passed |
| Prime workspace | `~/prime-dgx-agent/` | policy and validation gate installed |
| Browser backend | `prime-web.service`, 127.0.0.1:7681 | ttyd 1.7.4, enabled and active |
| Dashboard API | `prime-dashboard-api.service`, 127.0.0.1:8765 | enabled, active, health/state passed |
| Authenticated HTTPS | Nginx, 127.0.0.1 and 172.16.253.231:8443 | private-source ACL + TLS + PAM |

Nginx retains its explicit private listeners. A systemd drop-in first waits up
to 120 seconds for `172.16.253.231` to become a local address and then runs the
distribution configuration test. This repairs the observed reboot race without
falling back to a wildcard/public listener.

Both vLLM containers use image
`vllm/vllm-openai:v0.27.1-aarch64-cu129-ubuntu2404`, local image ID
`sha256:22c56c3a39c4858f6cff09beb337544ac2732ca087908ffdde8ed953174b1f6e`.
Qwen's downloaded checkpoint size was reported by vLLM as 21.82 GiB.

## Configuration

Nemotron uses an 81,920-token cap, 12 GiB FP8 KV cache, two sequences, Marlin
MoE, prefix caching, FlashInfer Mamba, and three DSpark speculative tokens. Qwen
uses a 65,536-token cap, 8 GiB FP8 KV cache, two sequences, Marlin, chunked
prefill, async scheduling, and an 8,192-token batch cap. These are intentionally
conservative dual-residency settings.

Prime defaults to `spark-nemotron/nemotron-3.5-lightning`, advertises Qwen as a
text-and-image model, defaults to low thinking, and disables Prime telemetry.
The project policy requires paper-only trading and gated continual improvement.

Non-secret deployed-file SHA-256 values:

- Nemotron launcher: `1dbe9eef7e80aa63ef2cf13f8e21843687b169767475bb2bfcb8a579d6d0c5b8`
- Qwen launcher: `7d45793fcc414f763f99ea74e228c7587263b167a08f1aaefb39117c712711c4`
- Prime models registry: `750cccfbcb84314f8e8b7b773749d8245b84bb718d2f4da4f3d01175622338dd`
- Prime settings: `3ae303a94014c036e29a71645eb40c5325fa16d61c0091bd4f45d54b024f7799`
- Operating policy: `fef78438b65d9faa35fa20277470f78d1a16cf31f6d77a401b1e84576d8fb216`
- Validation gate: `208595914e2a005a971170989c746285fa1aa6ace84219e9b61ffdbf0f882807`

## Acceptance evidence

- Both `/v1/models` endpoints returned their intended served-model name.
- Direct text inference passed for both models.
- Qwen correctly inspected a supplied PNG and reported its dominant color.
- Prime explicit-provider tests passed for both models; its unqualified default
  produced `DEFAULT_ROUTE_OK` through Nemotron.
- Both user services are enabled and active. After the 2026-08-24 reboot they
  started through user lingering; Nginx alone failed due to address assignment
  ordering and was repaired with the bounded pre-start wait. A second physical
  reboot was not performed during repair.
- The model ports are loopback-only.
- The ttyd backend returned HTTP 200 and is loopback-only. The authenticated
  HTTPS endpoint returned 401 without credentials from both the Spark and a LAN
  Mac and advertised the expected PAM realm. The generic
  system-wide ttyd unit installed by Ubuntu was disabled; only the scoped user
  service is enabled.
- Linux reported 39.1 GiB available memory (32.15%) after the 81,920-token
  Nemotron restart and a warm generation. The validation script passed its
  dynamic 20%-of-system-memory floor (about 24.3 GiB on this Spark).

## Rollback

The complete pre-change recovery artifact is
`/var/backups/dgx-spark-baseline-20260823T154649-0500`; verify its checksums and
follow `SPARK_BASELINE.md` before restoring. For a narrow runtime rollback, stop
and disable `vllm-qwen36.service`, restore the captured Nemotron files from the
protected baseline, remove or deactivate the Prime launcher/configuration, then
start the original Nemotron service and rerun its health test. Do not delete the
current configuration until the restored service is verified. Record any
rollback as a new wiki version rather than editing v0011.

To roll back only browser access, run
`systemctl --user disable --now prime-web.service`, remove the Prime Nginx site
and PAM policy, reload Nginx, and optionally remove the added packages. This does
not affect Prime's terminal interface or either model.

## Browser access

Open `https://172.16.253.231:8443` from a LAN or routed private-VPN client.
Accept the one-time warning for the initial self-signed certificate, then sign
in as `dbyte` using the Spark system password.
PAM protects the web interface. Nginx permits only loopback, RFC1918 networks,
and the carrier-grade `100.64.0.0/10` range commonly used by VPN overlays, then
denies all other sources. The service permits at most two clients, checks
WebSocket origin, and launches only `prime-dgx` in `~/prime-dgx-agent`.

Direct LAN access rejects missing credentials with HTTP 401. Authenticated
browser validation succeeded without exposing the user's PAM password.

Browser service SHA-256:

- terminal systemd unit: `82cfcd562beec19c2f7cf42de636509cab8b795b292bf1f9c9247af54376379d`
- dashboard API systemd unit: `0923209dbe0fb199dc64b7ce044922190ca95922f04809330132f9693f508a80`
- dashboard API: `c3030ac9b01957f9116f6a65fd78e34e702d115af4c07e59725d6c580faa627c`
- Nginx site: `44f170999acf537fb8d6b84c0835102be42c0c273e0ede994798f2ccc8102ec9`
- PAM policy: `032465f28bb702fb39373046fb10ddc7bdca6b508f8ccbd719a9dc7b5ed0ab96`
- updated validation gate: `0c4f60d16151ce05f9f5d751bb7f38bcb24f735fbdf0e4a5cf4a6fc10c1dc7ed`

The self-signed certificate is valid from 2026-08-23 through 2028-11-25. Its
SHA-256 fingerprint is
`A7:25:78:D4:79:51:60:23:2C:91:99:B0:63:44:13:95:4E:6A:13:D2:CB:AF:A1:ED:6A:FD:0D:62:CD:94:9D:C8`.
With explicit user approval, Nginx's `www-data` account is a supplementary member
of `shadow` (GID 42), which Ubuntu's PAM implementation requires here to validate
other system users. All inspected workers inherited the group after restart. The
tradeoff is that an Nginx compromise could read password hashes for offline
attack. Revoke with `sudo gpasswd -d www-data shadow` followed by an Nginx
restart; doing so disables working PAM authentication in this design.

Nginx serves the dashboard at `/`, proxies its API at `/api/`, embeds ttyd under
`/terminal/`, and validates `/terminal/ws` origins against approved HTTPS names
before proxying. ttyd's own `--check-origin` is intentionally disabled: behind this
reverse proxy it compared the external HTTPS origin with its internal loopback
host and rejected every valid WebSocket. End-to-end validation observed a ttyd
WebSocket connection, a spawned Prime process, and an active browser terminal.
Dashboard controls and accounting semantics are detailed in `PRIME_DASHBOARD.md`.
The API proxy permits request bodies up to 100 MiB and disables request buffering
for streamed file uploads; all other upload limits and private storage rules are
enforced by the loopback dashboard API.

## Remaining commissioning work

- Configure the OpenAI Responses API route without putting its key in this wiki.
- Build frozen domain evaluations and conduct a long dual-load soak/benchmark.
- Add validated CAD/slicer, timestamped market-data, portfolio, and paper-broker
  toolchains. Live trading remains outside the authorized scope.
