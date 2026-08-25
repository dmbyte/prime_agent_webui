# ADR-0036: Encode the photo-supported INV001 hardware stack conservatively

- Status: accepted
- Date: 2026-08-24
- Supersedes: none
- Superseded by: none

## Context

The owner supplied several photographs of the installed iUniker INV001 HAT and
its brass spacer. The HAT photographs support the previously reported 85 mm Pi
length and standard Raspberry Pi mounting pattern. The spacer photographs are
consistent with the common nominal 16 mm HAT standoff, but the digital caliper
display is off, so they cannot justify a sub-millimeter measurement.

## Decision

Retain the 85 x 56.5 mm HAT plan envelope and 100.6 x 71.6 x 42.4 mm enclosure.
Represent the vertical stack explicitly as a nominal 16 mm standoff, 1.6 mm HAT
PCB, and 7.4 mm topside component/wiring/air allowance. This preserves the prior
25 mm Pi-top-to-envelope-top assumption and leaves 8 mm between that conservative
envelope and the base rim.

Record the photographic basis and its measurement limitation in the generated
validation report. Continue to require a physical fit coupon before the final
PETG print.

## Consequences

The printable shell does not change, because the photographic evidence supports
the existing envelope. The source and validation output now expose the actual
stack assumptions, making a later direct measurement easy to substitute. The
model does not claim that the photos prove an exact 16.00 mm spacer.

## Validation

Regenerate all outputs and verify that all three meshes remain single-body,
watertight, winding-consistent, and positive-volume. Re-run the installed X2D
PETG Basic slice check and confirm no supports, warnings, or filament changes.

## Reversal conditions

Update the standoff or component allowance if a powered-down direct measurement
of the assembled stack differs or if the first fit coupon reveals interference.
