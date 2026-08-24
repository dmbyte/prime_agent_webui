# DGX Spark Pre-Change Baseline

Captured: 2026-08-23T15:49:11-05:00  
Host: `spark-c562` (`172.16.253.231`)  
Remote administrator: `dbyte` (passwordless sudo verified)  
Baseline status: complete and checksum-verified

## Recovery artifact

- Root-only directory on Spark:
  `/var/backups/dgx-spark-baseline-20260823T154649-0500`
- Protected configuration archive: `configuration.tar.gz`
- Archive size: 1,377,975,922 bytes (about 1.3 GiB)
- Archive SHA-256:
  `dbac814e640e41293ffc589b5ece0489d7f514e81948b078d227dc66b7fba953`
- Manifest: `SHA256SUMS`
- Manifest SHA-256:
  `63bf583d731159f0ac9f08c5757d673ebc3d140c5a7d0f0e60cd84b91fd1bd2f`
- Verification: every manifest entry passed `sha256sum -c`.
- Archive warnings: only tar's expected removal of leading `/` path prefixes.
- Permissions: directory and contents are root-only.

The protected archive contains system/service/network configuration plus the
current Hermes and vLLM configuration, including credential-bearing configuration
files. Secrets were not displayed or copied into the wiki. Model caches, session
history, logs, and ordinary user data were not intentionally archived.

Do not restore the tar archive wholesale onto a running system. Compare the
target files, stop affected services, restore only the required paths, preserve
ownership/modes, reload systemd where applicable, and validate each service. A
full OS/disk rollback requires an image backup; this artifact is a configuration
rollback baseline, not a complete 470 GB filesystem image.

## Hardware and firmware

- Platform: NVIDIA DGX Spark, board P4242 A04
- Architecture: ARM64
- CPU: 20 cores total; 10 Cortex-X925 plus 10 Cortex-A725
- Unified memory: 127,600,752 kB visible (about 121 GiB reported by `free`)
- NUMA: one node
- GPU: NVIDIA GB10, Blackwell; C2C enabled; persistence enabled
- GPU driver: 580.173.02
- Driver-reported CUDA compatibility: 13.0
- VBIOS: 9A.0B.2D.00.00
- System firmware/BIOS: 5.36_0ACUM018, released 2025-08-06
- Secure Boot: enabled

At capture the GPU was 35°C, P0, about 10–13 W, and 0% utilized. A vLLM engine
held about 46,141 MiB. System memory was about 53 GiB used, 68 GiB available; the
16 GiB swap file was unused.

## Operating system

- Ubuntu 24.04.4 LTS (Noble)
- Kernel: `6.17.0-1029-nvidia`
- Kernel build: `#29-Ubuntu SMP PREEMPT_DYNAMIC Wed Jul 1 00:13:52 UTC 2026`
- Boot uptime at first capture: 9 days, 6 hours, 59 minutes
- No failed systemd units
- Package manifests, manual apt selection, snaps, and system Python freeze are in
  the protected baseline and individually checksummed.

## Storage

- One Samsung MZALC4T0HBL1-00B07 NVMe, nominal 4.10 TB / 3.7 TiB block device
- Firmware: NXHB202Q
- Layout: 298 MiB FAT32 EFI partition plus ext4 root partition
- Root usage: 470 GiB used, 3.1 TiB available (14%)
- Swap: `/swap.img`, 16 GiB, unused
- NVMe SMART: 32°C, 100% spare, 0% percentage used, no media/error-log entries
- Lifetime counters: about 24.87 TB read, 14.10 TB written, 137 power-on hours,
  113 power cycles, and 26 unsafe shutdowns

## Network and exposure

- Wired interface: `enP7s7`, static `172.16.253.231/24`
- Default route and DNS: `172.16.253.1`
- Wi-Fi interface down
- Docker bridge: `172.17.0.1/16`
- UFW status: inactive
- Docker nftables rules publish vLLM port 30000 to all IPv4 and IPv6 interfaces
- Notable listening TCP ports: 22 (SSH), 80 (nginx), 111/2049 (RPC/NFS), 8787
  (Hermes WebUI Python process), and 30000 (vLLM)

This is a broad LAN exposure and should be reviewed before adding credentials or
financial tools. No firewall change was made during capture.

## Container and inference state

- Docker Engine/client: 29.2.1
- containerd: 2.2.1
- runc: 1.3.4
- NVIDIA Container Toolkit: 1.20.0
- Running container: `vllm-nemotron35`
- Image: `vllm/vllm-openai:v0.27.1-aarch64-cu129-ubuntu2404`
- Image ID: `sha256:22c56c3a39c4858f6cff09beb337544ac2732ca087908ffdde8ed953174b1f6e`
- Image digest:
  `sha256:a20437a6f671c258abbe354858420c1b0ee93c12f5a64aa92473c0ea2a677cc0`
- Restart policy: `unless-stopped`; IPC host; 32 GiB shared memory; all GPUs
- Hugging Face cache bind-mounted read/write from `/home/dbyte/.cache/huggingface`
- Port mapping: host `0.0.0.0/[::]:30000` to container 30000

Active model configuration:

- Target: `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4`
- Drafter: matching `NVFP4-DSpark`
- DSpark speculative tokens: 3
- MoE: Marlin; Mamba: FlashInfer aligned mode
- FP8 KV cache and prefix caching enabled
- Reasoning parser: `nemotron_v3`
- Tool parser: `qwen3_coder`; automatic tool choice enabled
- Maximum model length: 65,536
- Maximum sequences: 4
- GPU memory utilization setting: 0.78
- Explicit KV cache budget: 24 GiB

The OpenAI-compatible `/v1/models` endpoint responded successfully and reported
the expected model and 65,536-token limit.

Cached Hugging Face content totals about 97 GiB and includes Nemotron 3.5 target
and DSpark, Nemotron 3 Super 120B, and Hermes 4 70B artifacts. Model snapshot
revision identifiers are retained in the protected inventory.

Additional retained container images include TensorRT-LLM 1.3.0rc14, SGLang
Spark, CUDA 13.0.1 base, Ubuntu, and curl; exact digests are in the manifest.

## Existing Hermes installation

- `hermes-webui.service` is enabled and active under user/group `dbyte`.
- Direct process: Python WebUI bootstrap bound to `0.0.0.0:8787`.
- Restart policy: on failure.
- Hermes agent repository commit:
  `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`
- Agent branch was 1,151 commits behind `origin/main` at capture and contained
  untracked design/research artifacts; those files were not modified.
- Hermes WebUI repository commit:
  `0a31a4a1e2a0977d55673b91ca15eea73d2e06c9`
- WebUI branch was 435 commits behind its origin.
- Service reported active, but direct HTTP probes to port 8787 returned an empty
  response. This baseline records it as running but not application-healthy.
- Ollama 0.19.0 client is installed; `ollama.service` is disabled/inactive.

Hermes configuration, environment, authentication material, WebUI settings,
application trees, repository state, systemd unit, and prior local backups are
covered by the protected baseline without exposing their contents here.

## Capture scope and limits

Captured and checksummed:

- Hardware/firmware, CPU, memory, GPU, NVMe health, boot command line
- Partitions, filesystems, mounts, and swap
- Addresses, routes, DNS, listeners, firewall/nftables state
- systemd units, enabled state, failures, and timers
- apt/dpkg, snap, Python, Docker image/container/network/volume manifests
- Sanitized container configuration and exact runtime/image identifiers
- Current system, network, nginx, SSH-server, Docker, systemd, Hermes, and vLLM
  configuration archive
- Crontabs, application Git revisions/status, and endpoint health responses

Not captured as recoverable data:

- Full disk image, boot partition image, model weights, Docker layer contents,
  ordinary home-directory data, session conversations, logs, or external service
  state
- Plaintext secrets in the wiki

Capture procedure is reproducible from `scripts/capture_spark_baseline.sh`.

