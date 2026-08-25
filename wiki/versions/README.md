# Version Snapshots

These files are immutable, human-readable captures of material project states.
The highest numbered snapshot is normally current; confirm against
`../README.md` and `../CURRENT_STATE.md`.

| Version | Date | Summary |
|---|---|---|
| [v0044](v0044.md) | 2026-08-24 | Added private, bounded file uploads to the conversation workspace |
| [v0043](v0043.md) | 2026-08-24 | Increased Nemotron context to 81,920 tokens without enlarging its KV cache |
| [v0042](v0042.md) | 2026-08-24 | Made private dashboard startup tolerate delayed LAN address assignment |
| [v0041](v0041.md) | 2026-08-24 | Corrected right-click deletion to target the clicked row |
| [v0040](v0040.md) | 2026-08-24 | Added guarded, recoverable right-click conversation deletion |
| [v0039](v0039.md) | 2026-08-24 | Hid attachment-command artifacts from Conversations |
| [v0038](v0038.md) | 2026-08-24 | Made the minimized overlay control show an expand symbol |
| [v0037](v0037.md) | 2026-08-24 | Preserved explicit attach while removing all UI attach behavior |
| [v0036](v0036.md) | 2026-08-24 | Retired interfering browser session attachment |
| [v0035](v0035.md) | 2026-08-24 | Moved Stop task from the overlay to the main conversation |
| [v0034](v0034.md) | 2026-08-24 | Moved activity to the top and added searchable provider switches |
| [v0033](v0033.md) | 2026-08-24 | Added a guarded single-task stop control |
| [v0032](v0032.md) | 2026-08-24 | Added an optional read-only attached console for active tasks |
| [v0031](v0031.md) | 2026-08-24 | Added tabbed, resizable background activity overlay |
| [v0030](v0030.md) | 2026-08-24 | Grouped configured Usage models into collapsible provider roll-ups |
| [v0029](v0029.md) | 2026-08-24 | Automatically discovered authenticated Prime models for Usage |
| [v0028](v0028.md) | 2026-08-23 | Configured OpenAI GPT-5.4; billing credits remain required |
| [v0027](v0027.md) | 2026-08-23 | Corrected OpenAI API-key model/provider mapping |
| [v0026](v0026.md) | 2026-08-23 | Added zero-usage rows and corrected OpenAI configuration status |
| [v0025](v0025.md) | 2026-08-23 | Verified why Qwen and OpenAI have no Usage rows |
| [v0024](v0024.md) | 2026-08-23 | Grouped power with utilization and temperatures together |
| [v0023](v0023.md) | 2026-08-23 | Combined per-model tokens and spend for today and 30 days |
| [v0022](v0022.md) | 2026-08-23 | Added constrained click-to-resume conversations |
| [v0021](v0021.md) | 2026-08-23 | Renamed the private repository to dmbyte/prime_agent_webui |
| [v0020](v0020.md) | 2026-08-23 | Published the project to private GitHub repository dmbyte/dgx-spark |
| [v0019](v0019.md) | 2026-08-23 | Prepared a secret-conscious private GitHub backup |
| [v0018](v0018.md) | 2026-08-23 | Added sanitized topics and latest-chat timestamps |
| [v0017](v0017.md) | 2026-08-23 | Renamed user-facing sessions as conversations |
| [v0016](v0016.md) | 2026-08-23 | Added metadata-only session view and live Spark telemetry |
| [v0015](v0015.md) | 2026-08-23 | Added settings, tokenomics, and provider-spend dashboard |
| [v0014](v0014.md) | 2026-08-23 | Repaired authenticated reverse-proxied WebSocket access |
| [v0013](v0013.md) | 2026-08-23 | Enabled Nginx PAM account retrieval after explicit approval |
| [v0012](v0012.md) | 2026-08-23 | Diagnosed PAM failure without expanding Nginx privilege |
| [v0011](v0011.md) | 2026-08-23 | Enabled PAM browser access for private LAN/VPN clients |
| [v0010](v0010.md) | 2026-08-23 | Assessed and deferred unsafe direct public exposure |
| [v0009](v0009.md) | 2026-08-23 | Added PAM authentication and TLS to Prime browser access |
| [v0008](v0008.md) | 2026-08-23 | Added private SSH-tunneled Prime browser access |
| [v0007](v0007.md) | 2026-08-23 | Commissioned Prime with concurrent Nemotron and Qwen NVFP4 |
| [v0006](v0006.md) | 2026-08-23 | Captured verified pre-change Spark baseline |
| [v0005](v0005.md) | 2026-08-23 | Selected Prime as the continually improving core |
| [v0004](v0004.md) | 2026-08-23 | Reframed as multimodal personal agent with trading safeguards |
| [v0003](v0003.md) | 2026-08-23 | Selected Prime Agent as prototype scaffold |
| [v0002](v0002.md) | 2026-08-23 | Recommended two-model DGX Spark agent architecture |
| [v0001](v0001.md) | 2026-08-23 | Initialized the durable project wiki |

To restore an earlier state, follow `../OPERATING_GUIDE.md`; document the result
as a new version instead of modifying an old snapshot.
