# ADR-0038: Adapt the v14 button and perimeter ventilation pattern

- Status: accepted
- Date: 2026-08-24
- Supersedes: the separate LED hole and vent pattern in ADR-0037
- Superseded by: none

## Context

The owner supplied CaseLower v14, CaseUpper v14, PowerButton v14, and Spacer_v14
STLs as physical-layout references. Mesh inspection found a 10.6 x 8.3 x 5.6 mm
button envelope at the short end, a roughly 9 x 4 mm stem opening, and a 3.5 x
1.5 mm offset oval light window through the button itself. The shells use long
floor slots, a honeycomb top, and narrow wall slots. The owner also stated that
the new enclosure does not need a microSD access cutout.

## Decision

Redesign the printable actuator around the reference envelope, integrate its LED
window into the button face, and center it 11.5 mm toward the USB-C/HDMI side of
the short end. Remove the separate LED wall hole and the microSD opening.

Adapt the reference cooling language to the taller iUniker enclosure: use long
parallel floor intakes, a honeycomb lid exhaust, and 12 mm vertical exhaust slots
around all four upper walls. Retain the existing iUniker stack height, connector
openings, PETG clearances, and fasteners rather than copying the reference shell.

## Consequences

The status light is visible through the pressable actuator, the end wall is
stiffer without a microSD slot, and airflow is distributed around the full upper
stack. The button is shorter and wider than the previous generic plunger. Physical
button travel and LED visibility remain fit-coupon requirements.

## Validation

Regenerate every output, require single-body watertight positive-volume meshes,
and run the installed X2D/PETG slice check with no supports or warnings. Inspect
the preview for continuous vent webs and verify the first physical fit coupon
before printing the entire base in PETG.

## Reversal conditions

Adjust the exposed actuator dimensions if the reference-derived fit does not
match the owner's Pi. Restore a microSD opening only if future access is required.
