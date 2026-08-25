# ADR-0035: Center the equal-length Pi and INV001 in a compact shell

- Status: accepted
- Date: 2026-08-24
- Supersedes: the 90 mm length assumption within ADR-0033
- Superseded by: none

## Context

The enclosure initially reserved a conservative 90 mm length because an iUniker
INV001 production drawing was unavailable. The owner then physically identified
the relevant HAT as the same 85 mm length as Raspberry Pi 5. Keeping the extra
length would waste material and leave unnecessary dead space behind the stack.

## Decision

Use an 85 mm INV001 length, center both equal-length boards, and reduce the clear
internal length to 95 mm. Keep the 66 mm internal width for airflow, connector
recess, and corner fasteners. Move lid-tower centers nearer the rounded outer
corners so they remain outside the centered PCB outline and mounting standoffs.

## Alternatives considered

- Retaining the 102 mm cavity was rejected because the confirmed hardware does
  not need its 17 mm of excess longitudinal clearance.
- Reducing both length and width to near-board size was rejected because the USB-C
  and HDMI shells, ventilation, lid skirt, and screw towers need side clearance.

## Consequences

The case is 7 mm shorter and uses less PETG while preserving airflow and port
access. The physical board width, connector protrusion, corner radius, and stacked
height remain measurement gates; equal nominal length alone does not validate
every feature.

## Validation

Regenerate and re-run mesh and X2D slice validation. Confirm the external length
is 100.6 mm, the HAT envelope records 85 mm, all meshes remain manifold, and the
X2D plate produces no support features or warnings. Verify tower-to-PCB clearance
on the 12 mm fit coupon before printing the full base.

## Reversal conditions

Restore or adjust longitudinal clearance if direct caliper measurements show that
the carrier, solder mask, connector, or SSD retainer extends beyond 85 mm.
