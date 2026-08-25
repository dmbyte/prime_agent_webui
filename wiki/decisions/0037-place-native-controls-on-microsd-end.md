# ADR-0037: Place the native controls on the microSD end

- Status: accepted
- Date: 2026-08-24
- Supersedes: the connector-side actuator placement in ADR-0033
- Superseded by: none

## Context

The first enclosure revision incorrectly placed the native-button actuator along
the USB-C/HDMI side near the board's middle. The owner clarified that the button
is at the short end near the microSD slot and that the LED is immediately beside
it. A Raspberry Pi 5 board close-up confirms the switch is on the short edge near
the USB-C corner, with the LED between the switch and that corner. Raspberry Pi's
mechanical drawing warns that component positions are approximate and should be
checked against a physical board.

## Decision

Move the captive actuator opening to the short microSD end. Parameterize its
center at Y = -14.0 mm on the centered Pi board, toward the USB-C/HDMI corner.
Add a 2.9 mm round LED sight hole at Y = -19.5 mm, immediately toward that corner.
Place both at Z = 7.2 mm in the enclosure coordinate system. Rotate the separate
button part through the end wall during assembly.

## Consequences

The button now matches the physical edge and the status light remains visible.
The microSD opening remains centered and separate. Exact Y/Z alignment still
requires the prescribed short fit coupon because the official drawing does not
provide production-grade switch and LED coordinates.

## Validation

Regenerate all parts; check each mesh for one positive-volume watertight body.
Run the installed X2D/PETG slice validation and require no support features,
warnings, or filament changes. Physically verify free button travel and LED
visibility before printing the full case in PETG.

## Reversal conditions

Adjust the three exposed control constants if a direct powered-down measurement
or fit coupon shows positional error. Restore the old placement only if the board
under test is physically different from the Raspberry Pi 5 reference layout.
