# ADR-0034: Tune the enclosure for support-free X2D PETG printing

- Status: accepted
- Date: 2026-08-24
- Supersedes: none
- Superseded by: none

## Context

The enclosure will be printed from Bambu PETG Basic on a Bambu Lab X2D. The stock
main nozzle is assumed to be 0.4 mm. PETG benefits from intentional sliding
clearance and should not be asked to bridge the original 54 mm-wide combined
Ethernet/USB opening. The X2D can use a second support nozzle, but removable
support would add switching and cleanup without improving this enclosure.

## Decision

Use the X2D left/main nozzle alone and the built-in Bambu PETG Basic preset. Set
case walls to 2.8 mm, lid clearance to 0.35 mm per side, and M3 self-tapping pilot
diameter to 2.7 mm. Divide the connector end into three bays with structural ribs,
keeping the longest horizontal bridge below 17 mm. Preserve support-free print
orientations and document a 0.20 mm process starting point rather than embedding
temperature values that could drift from Bambu's maintained material preset.

## Alternatives considered

- Keeping the combined connector opening was rejected because its long PETG
  bridge could sag into plug clearance.
- Printing disposable or soluble supports with the auxiliary nozzle was rejected
  because the geometry can be made self-supporting.
- Hard-coding nozzle and bed temperatures was rejected in favor of the printer's
  maintained, RFID-aware Bambu PETG Basic preset.

## Consequences

The enclosure is more robust and repeatable on the specified machine, and it no
longer depends on support-interface behavior. The separated bays require physical
confirmation that all three actual connector shells and plugs align with the
modeled openings. Different nozzle sizes require revisiting wall and clearance
parameters rather than blindly reusing this tuning.

## Validation

All exported meshes must retain the existing manifold checks. Bambu Studio must
show no generated support, no wall bridge longer than 17 mm, and all parts within
the left-nozzle build area. A 12 mm-high base fit coupon must precede the complete
PETG print.

## Reversal conditions

Retune these values if the actual nozzle is not 0.4 mm, dimensional calibration
shows a materially different fit, or connector plugs conflict with the new ribs.
