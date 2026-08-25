# Raspberry Pi 5 + iUniker INV001 NVMe HAT+ case

This is a parametric, 3D-printable enclosure for a Raspberry Pi 5 with the
iUniker INV001 PCIe-to-M.2 NVMe HAT+. It is sized for 2230, 2242, 2260, and 2280
NVMe drives and for the official Raspberry Pi 5 Active Cooler under the HAT.

## Design features

- Long parallel intake slots below the Pi and NVMe drive.
- A large honeycomb lid exhaust plus narrow vertical slots around all four upper
  walls, patterned after the supplied v14 reference enclosure.
- Open access to USB-C power, both micro-HDMI connectors, four USB ports,
  and Ethernet.
- A separate captive printed plunger that operates the Pi 5 native power button;
  it requires no wiring.
- The actuator is on the short end near the USB-C corner. Its 10.6 x 5.6 mm face
  includes an offset oval window for the immediately adjacent bi-colour LED.
- No microSD access cutout, per the owner's requirement.
- Four M3 x 8 mm self-tapping lid screws and four recessed M2.5 mounting holes.
- PETG-tuned 2.8 mm walls, 0.35 mm-per-side lid clearance, 2.7 mm M3 pilots, and
  separated USB/Ethernet bays to avoid a long unsupported bridge.
- Rounded 100.6 x 71.6 x 42.4 mm exterior; approximately 95 x 66 x 37.6 mm
  clear interior before supports.
- Photo-supported nominal 16 mm HAT standoffs, with a conservative 25 mm
  Pi-top-to-stack-top envelope and 8 mm of air space below the base rim.
- Support-free default print orientation for all three parts.

## Files

- `generate_case.py` — editable source of truth and all fit parameters.
- `requirements.txt` — pinned generator and mesh-validation dependencies.
- `X2D_PETG_BASIC.md` — X2D plate layout and Bambu Studio process settings.
- `validate_x2d_slice.py` — resolves Bambu's bundled factory profiles and runs a
  temporary, no-G-code-retained X2D slice check.
- `output/pi5_iuniker_case_base.stl` — base, printed floor-down.
- `output/pi5_iuniker_case_lid.stl` — lid, printed outside-face-down.
- `output/pi5_iuniker_case_power_button.stl` — native-button plunger.
- `output/pi5_iuniker_case_assembly.glb` — colored exploded preview.
- `output/pi5_iuniker_case_preview.png` — quick visual preview.
- `output/validation.json` — mesh integrity, volume, triangle, and size report.
- `output/x2d_petg_basic_slice_validation.json` — verified X2D/PETG slice summary.

## Print settings

For Bambu PETG Basic on the X2D with its stock 0.4 mm main nozzle, follow
[`X2D_PETG_BASIC.md`](X2D_PETG_BASIC.md). The short generic guidance below is for
other printers and materials.

- Material: PETG, ASA, or ABS is preferred for sustained Pi 5 temperatures.
  PLA is acceptable for a fit prototype.
- Layer height: 0.20 mm.
- Walls: 4 perimeters.
- Top/bottom: 5 layers.
- Infill: 20–30% gyroid or cubic.
- Supports: none for the supplied orientations.
- Hole compensation: enable it if your printer undersizes holes.

## Hardware and assembly

1. Print the base, lid, and power-button plunger in their supplied orientation.
2. Test the bare Pi and NVMe HAT together outside the enclosure first.
3. Insert the power-button plunger from inside the short microSD-end wall, with
   its small nose facing the Pi's native button. Confirm it moves freely, does not
   hold the Pi button down, and leaves the integrated LED window unobstructed.
   File the 1.6 mm nose shorter if necessary.
4. Place the Pi/HAT stack on the four base pads. Use M2.5 screws from below with
   the stack's existing standoffs or nuts. Screw length depends on that hardware.
5. Confirm that the PCIe cable, active cooler, SSD, and all connector shells clear
   the case before applying power.
6. Fit the lid skirt inside the base and secure it with four M3 x 8 mm self-tapping
   screws. Stop as soon as each screw is snug.

## Mandatory fit check

iUniker does not publish a production mechanical drawing for INV001, and reseller
package dimensions are not board dimensions. The owner confirmed that this HAT is
the same 85 mm length as the Pi 5. Owner-supplied photos also support the standard
Pi mounting pattern and a nominal 16 mm brass HAT standoff. The photographed
caliper display was off, so the pictures are not treated as sub-millimeter
metrology. Before the final PETG print, measure the actual assembled hardware and
compare it with the parameters at the top of `generate_case.py`, especially:

- `HAT_ENVELOPE`
- `HAT_STANDOFF_H` and `HAT_TOP_ABOVE_PI`
- `PI_UNDERSIDE_Z`
- `PI_LEFT_X`
- `POWER_BUTTON_Y`, `POWER_LED_OFFSET_Y`, and `POWER_CONTROL_Z`

Print the base in inexpensive PLA first or slice only the first 12 mm as a port
and mounting-hole fit coupon. Raspberry Pi's own mechanical drawing also labels
its dimensions approximate, so a physical fit check remains necessary.

## Regeneration

The generator needs Python 3.12+, `numpy`, `Pillow`, `trimesh`, and `manifold3d`.

```sh
python3 generate_case.py
```

All dimensions are millimetres. Generated STLs are replaced in `output/`.
