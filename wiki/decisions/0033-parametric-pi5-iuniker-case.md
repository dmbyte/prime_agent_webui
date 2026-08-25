# ADR-0033: Use a measured parametric shell and native-button plunger for the Pi enclosure

- Status: accepted
- Date: 2026-08-24
- Supersedes: none
- Superseded by: none

## Context

The enclosure must hold a Raspberry Pi 5, official Active Cooler, and iUniker
INV001 M.2 HAT+ with NVMe drives up to 2280 length. It needs high airflow and an
external power control. Raspberry Pi publishes approximate board drawings, but
iUniker does not publish a production mechanical drawing for INV001; reseller
package dimensions cannot safely define the carrier PCB.

## Decision

Use a source-controlled parametric generator with a conservative adjustable HAT
envelope. Make the case a support-free base and inset-skirt lid secured with four
M3 screws. Vent the bottom, lid, rear, and unused end-wall regions while preserving
continuous structural ribs. Operate the Pi 5 native power switch with a captive
printed plunger rather than adding a wired panel switch.

## Alternatives considered

- A fixed imported model was rejected because the exact iUniker production CAD is
  unavailable and a non-parametric mesh is costly to correct after measurement.
- Snap latches were rejected because their reliability varies materially with
  printer calibration and material creep.
- A wired panel-mount switch remains possible, but it adds parts, soldering, and
  electrical assembly when the Pi already provides a native momentary button.

## Consequences

The enclosure is easy to resize, re-export, and reopen without stressing clips.
It uses four lid screws and requires the small printed button part. The first
final-material print must wait for physical confirmation of the carrier envelope,
stack height, port alignment, and button nose length.

## Validation

Regeneration must produce positive-volume, single-body, watertight, winding-
consistent base, lid, and button meshes. Before release, slice all parts, print a
low-cost fit coupon or PLA prototype, test every port, confirm that the button is
not preloaded, and run a sustained thermal load with the lid installed.

## Reversal conditions

Replace the assumed envelope with an official iUniker drawing when available.
Use a panel switch if physical tests show that a tolerant captive plunger cannot
reliably actuate the native switch across supported Pi revisions.
