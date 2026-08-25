# Bambu X2D + Bambu PETG Basic print setup

This setup assumes the stock 0.4 mm nozzle in the X2D left/main hotend. The case
was regenerated with seven-nozzle-width 2.8 mm walls, 0.35 mm lid-skirt clearance
per side, a 2.7 mm M3 pilot, and separated Ethernet/USB bays whose longest bridge
is under 17 mm. The 95 mm internal length uses the owner's confirmation that the
iUniker HAT is the same 85 mm length as the Pi 5.

## Bambu Studio setup

1. Select **Bambu Lab X2D 0.4 nozzle**.
2. Assign every part to the **left/main nozzle**.
3. Select the built-in **Bambu PETG Basic** filament preset. Use its RFID-loaded
   values when available instead of copying temperatures from a different PETG.
4. Start from the **0.20 mm Standard** process profile.
5. Keep supports disabled. The model is designed not to need either nozzle for
   support material.

Recommended process overrides:

| Setting | Value |
|---|---:|
| Wall loops | 4 |
| Top shell layers | 5 |
| Bottom shell layers | 5 |
| Sparse infill | 25% gyroid |
| Outer wall speed | 80 mm/s |
| Small perimeter speed | 50 mm/s |
| Bridge speed | 25 mm/s |
| Seam | Rear or nearest rear corner |
| Elephant-foot compensation | 0.15 mm |
| Supports | Off |

Keep the PETG Basic preset's nozzle, bed, flow, retraction, and cooling values
unless a filament calibration indicates otherwise. Do not enable the X2D heated
chamber mode for this print; an actively heated chamber is unnecessary here.

## Plate layout

- Base: floor flat on the plate.
- Lid: smooth exterior face flat on the plate, skirt upward.
- Button: broad 5.6 x 10.6 mm cap on the plate; add a 3 mm brim if the first-layer
  inspection shows poor adhesion.
- All three parts fit within the X2D's single-nozzle 256 x 256 mm area. Printing
  the base and lid separately makes first-layer inspection and recovery easier.

Use a clean Textured PEI or Smooth PEI plate appropriate to the selected Bambu
preset. PETG can bond aggressively to some smooth surfaces, so follow Bambu's
current plate/adhesive guidance for the installed plate.

## Before printing

- Dry the spool if Bambu Studio or the spool guidance calls for it, or if the
  filament pops, strings excessively, or leaves a rough surface.
- Run the X2D's normal bed and flow calibration.
- Slice and inspect every bridge and screw hole in preview mode.
- For the first hardware check, print the base only through 12 mm height. This
  verifies the board mounts, USB-C, HDMI, power-button travel, and integrated LED
  window with much less material than a complete case.

## After printing

- Let the plate cool before flexing it.
- Remove any first-layer lip from the lid skirt and connector openings.
- Test the lid without screws. It should slide in without force; lightly sand the
  skirt if needed instead of forcing PETG into the base.
- Start each M3 screw by hand. Tighten only until snug because repeated torque can
  strip printed PETG threads.
- Verify that the orange power plunger moves freely and does not preload the Pi's
  native button before powering the board.
