#!/usr/bin/env python3
"""Generate a vented Raspberry Pi 5 + iUniker INV001 NVMe HAT+ case.

The model is intentionally parameterized near the top of this file.  It uses
trimesh plus manifold3d for robust boolean geometry and exports print-ready STL,
a colored GLB assembly preview, and a PNG preview.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw


# ---------------------------------------------------------------------------
# Fit parameters (millimetres)
# ---------------------------------------------------------------------------
PI_BOARD = (85.0, 56.0, 1.6)
HAT_ENVELOPE = (85.0, 56.5)       # Owner/photos: same length as Pi 5
HAT_STANDOFF_H = 16.0             # Nominal size supported by supplied photos
HAT_PCB_T = 1.6
# Conservative allowance above the HAT PCB for the M.2 drive, connector, wiring,
# component tolerances, and air. Together these values preserve the former
# 25 mm Pi-top-to-stack-top envelope while making the physical stack explicit.
HAT_TOPSIDE_ALLOWANCE = 7.4
HAT_TOP_ABOVE_PI = HAT_STANDOFF_H + HAT_PCB_T + HAT_TOPSIDE_ALLOWANCE
PI_UNDERSIDE_Z = 5.4

INNER_X = 95.0
INNER_Y = 66.0
WALL = 2.8                         # Seven 0.4 mm nozzle widths for PETG
FLOOR = 2.4
BASE_H = 40.0
LID_T = 2.4
CORNER_R = 4.5

FIT_CLEARANCE = 0.35              # Per side; PETG-friendly sliding fit
SKIRT_T = 1.6
SKIRT_H = 4.2

VENT_W = 3.2
VENT_PITCH = 6.4

# The user-confirmed INV001 and Pi are equal in length, so both are centered.
PI_CENTER_X = 0.0
PI_LEFT_X = PI_CENTER_X - PI_BOARD[0] / 2
PI_CENTER_Y = 0.0

# Native Pi 5 controls on the short microSD end. Coordinates are relative to the
# centered board: negative Y is toward the USB-C/HDMI corner. The LED sits between
# the switch and that corner when the end is viewed from outside.
POWER_BUTTON_Y = -11.5
POWER_LED_OFFSET_Y = -2.15
POWER_CONTROL_Z = PI_UNDERSIDE_Z + 1.8

# Reference PowerButton v14 envelope and integrated light-window geometry.
BUTTON_FACE_H = 5.6
BUTTON_FACE_W = 10.6
BUTTON_DEPTH = 8.3
BUTTON_LIGHT_LENGTH = 3.5
BUTTON_LIGHT_WIDTH = 1.5

# Standard Raspberry Pi mounting pattern, measured from the Pi PCB lower-left.
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]

OUT_X = INNER_X + 2 * WALL
OUT_Y = INNER_Y + 2 * WALL
EPS = 0.04
OUT_DIR = Path(__file__).resolve().parent / "output"


def box(size, center=(0, 0, 0)):
    mesh = trimesh.creation.box(extents=size)
    mesh.apply_translation(center)
    return mesh


def cylinder(radius, height, center=(0, 0, 0), sections=48):
    mesh = trimesh.creation.cylinder(radius=radius, height=height, sections=sections)
    mesh.apply_translation(center)
    return mesh


def cylinder_x(radius, length, center=(0, 0, 0), sections=32):
    """Cylinder whose axis runs through an X-facing end wall."""
    mesh = cylinder(radius, length, (0, 0, 0), sections=sections)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    mesh.apply_translation(center)
    return mesh


def union(items):
    items = [m for m in items if m is not None]
    return trimesh.boolean.union(items, engine="manifold")


def difference(subject, cutters):
    cutters = [m for m in cutters if m is not None]
    if not cutters:
        return subject
    return trimesh.boolean.difference([subject, union(cutters)], engine="manifold")


def rounded_box_xy(x, y, z, radius, center=(0, 0, 0)):
    """Axis-aligned box with rounded vertical corners and flat top/bottom."""
    radius = min(radius, x / 2, y / 2)
    cx, cy, cz = center
    pieces = [
        box((x - 2 * radius, y, z), center),
        box((x, y - 2 * radius, z), center),
    ]
    for sx in (-1, 1):
        for sy in (-1, 1):
            pieces.append(cylinder(
                radius, z,
                (cx + sx * (x / 2 - radius), cy + sy * (y / 2 - radius), cz),
            ))
    return union(pieces)


def capsule_x(length, width, height, center):
    """Rounded slot/capsule running in X."""
    cx, cy, cz = center
    r = width / 2
    core = box((max(length - width, 0.01), width, height), center)
    caps = [
        cylinder(r, height, (cx - length / 2 + r, cy, cz), sections=24),
        cylinder(r, height, (cx + length / 2 - r, cy, cz), sections=24),
    ]
    return union([core, *caps])


def capsule_y(length, width, height, center):
    """Rounded slot/capsule running in Y."""
    mesh = capsule_x(length, width, height, (0, 0, 0))
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 0, 1]))
    mesh.apply_translation(center)
    return mesh


def hex_prism(radius, height, center):
    """Six-sided through-vent cutter."""
    return cylinder(radius, height, center, sections=6)


def capsule_z(length, width, depth, center, along="x"):
    """Rounded wall slot running horizontally; depth crosses the wall."""
    # Create in XY, then rotate so the short extrusion crosses a vertical wall.
    m = capsule_x(length, width, depth, (0, 0, 0))
    if along == "x":  # slot along X, extrusion originally Z -> wall depth Y
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    else:              # slot along Y, extrusion originally Z -> wall depth X
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    m.apply_translation(center)
    return m


def vertical_wall_capsule(length, width, depth, center, wall_axis):
    """Vertical capsule through a wall whose thickness axis is X or Y."""
    m = capsule_x(length, width, depth, (0, 0, 0))
    if wall_axis == "x":
        transform = trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0])
    elif wall_axis == "y":
        # Cyclic axis mapping: slot length X -> vertical Z, width Y -> wall X,
        # and extrusion Z -> wall depth Y.
        transform = np.array([
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ])
    else:
        raise ValueError("wall_axis must be 'x' or 'y'")
    m.apply_transform(transform)
    m.apply_translation(center)
    return m


def mounting_centers():
    return [
        (PI_LEFT_X + hx, -PI_BOARD[1] / 2 + hy)
        for hx, hy in PI_HOLES
    ]


def screw_boss_centers():
    # Sit close to the rounded enclosure corners, outside the Pi/HAT outline.
    inset = 2.80
    return [
        (sx * (INNER_X / 2 - inset), sy * (INNER_Y / 2 - inset))
        for sx in (-1, 1) for sy in (-1, 1)
    ]


def make_base():
    outer = rounded_box_xy(OUT_X, OUT_Y, BASE_H, CORNER_R,
                           center=(0, 0, BASE_H / 2))
    cavity = rounded_box_xy(INNER_X, INNER_Y, BASE_H - FLOOR + EPS,
                            max(CORNER_R - WALL, 1.0),
                            center=(0, 0, FLOOR + (BASE_H - FLOOR + EPS) / 2))
    base = difference(outer, [cavity])

    # Four PCB support pads. Screws enter from below and use the existing stack
    # standoffs/nuts; M2.5 clearance is deliberately generous at 2.9 mm.
    pads = []
    for x, y in mounting_centers():
        pads.append(cylinder(3.8, PI_UNDERSIDE_Z - FLOOR, (x, y, FLOOR + (PI_UNDERSIDE_Z - FLOOR) / 2)))
    base = union([base, *pads])

    # Lid screw towers, joined to the corners/walls. The PETG-tuned 2.7 mm blind
    # pilot holes accept M3 x 8 self-tapping screws from the lid.
    towers = []
    for x, y in screw_boss_centers():
        towers.append(cylinder(3.55, 11.0, (x, y, BASE_H - 5.5)))
    base = union([base, *towers])

    cutters = []
    for x, y in mounting_centers():
        cutters.append(cylinder(1.45, FLOOR + 2.0, (x, y, (FLOOR + 2.0) / 2 - EPS)))
        cutters.append(cylinder(2.65, 1.25, (x, y, 0.625 - EPS)))
    for x, y in screw_boss_centers():
        cutters.append(cylinder(1.35, 9.0, (x, y, BASE_H - 4.5 + EPS)))

    # USB-C and dual micro-HDMI openings on the connector side (Y negative).
    # Z dimensions allow connector tolerances.
    side_y = -OUT_Y / 2
    port_z = PI_UNDERSIDE_Z + 2.5
    ports = [
        (PI_LEFT_X + 11.2, 10.8, 7.2),
        (PI_LEFT_X + 25.8, 8.4, 6.2),
        (PI_LEFT_X + 39.2, 8.4, 6.2),
    ]
    for x, width, height in ports:
        cutters.append(box((width, WALL + 2.0, height), (x, side_y, port_z)))

    # Separate Ethernet/USB bays preserve vertical ribs and keep the longest
    # horizontal bridge below 17 mm. This is much cleaner in PETG than one 54 mm
    # opening while still providing shell and plug clearance.
    for y, bay_width in ((-19.5, 17.0), (0.0, 16.5), (19.5, 16.5)):
        cutters.append(box((WALL + 2.0, bay_width, 17.0),
                           (OUT_X / 2, y, PI_UNDERSIDE_Z + 6.0)))

    # The native Pi 5 button is on this short end, toward the USB-C/HDMI corner.
    # The reference-style printed actuator contains its own offset light window,
    # so this wall needs one shared stem/light opening and no microSD cutout.
    cutters.append(box((WALL + 2.2, 9.0, 4.2),
                       (-OUT_X / 2, POWER_BUTTON_Y, POWER_CONTROL_Z)))

    # Reference-style parallel floor intakes: long slots between the two rows of
    # board supports, repeated down the Pi/HAT length.
    for x in np.arange(-33.0, 33.1, 5.5):
        cutters.append(capsule_y(32.0, VENT_W, FLOOR + 1.0,
                                 (float(x), 0.0, FLOOR / 2)))

    # Vertical exhaust slots wrap around every upper wall. Their narrow rounded
    # crowns bridge cleanly in PETG while opening the NVMe/SSD hot-air layer.
    for x in np.arange(-40.0, 40.1, 8.0):
        for side in (-1, 1):
            cutters.append(vertical_wall_capsule(
                12.0, 3.0, WALL + 1.2,
                (float(x), side * OUT_Y / 2, 29.0), wall_axis="y"))

    for y in np.arange(-25.0, 25.1, 5.0):
        for side in (-1, 1):
            cutters.append(vertical_wall_capsule(
                12.0, 2.8, WALL + 1.2,
                (side * OUT_X / 2, float(y), 29.0), wall_axis="x"))

    base = difference(base, cutters)
    return base


def make_lid_print_orientation():
    # The outside top face sits on Z=0 for simple, support-free printing.  The
    # skirt and screw collars grow upward and point down in the assembled case.
    plate = rounded_box_xy(OUT_X, OUT_Y, LID_T, CORNER_R,
                           center=(0, 0, LID_T / 2))
    skirt_outer_x = INNER_X - 2 * FIT_CLEARANCE
    skirt_outer_y = INNER_Y - 2 * FIT_CLEARANCE
    skirt_outer = rounded_box_xy(skirt_outer_x, skirt_outer_y, SKIRT_H,
                                 max(CORNER_R - WALL - FIT_CLEARANCE, 1.0),
                                 center=(0, 0, LID_T + SKIRT_H / 2))
    skirt_inner = rounded_box_xy(skirt_outer_x - 2 * SKIRT_T,
                                 skirt_outer_y - 2 * SKIRT_T,
                                 SKIRT_H + 2 * EPS,
                                 1.0,
                                 center=(0, 0, LID_T + SKIRT_H / 2))
    skirt = difference(skirt_outer, [skirt_inner])

    collars = [cylinder(4.0, SKIRT_H, (x, y, LID_T + SKIRT_H / 2))
               for x, y in screw_boss_centers()]
    lid = union([plate, skirt, *collars])

    cutters = []
    # Honeycomb exhaust field follows the supplied upper-shell reference. The
    # 2 mm nominal webs remain robust with a 0.4 mm nozzle.
    for row, y in enumerate(np.arange(-24.0, 24.1, 8.0)):
        x_shift = 5.0 if row % 2 else 0.0
        for x in np.arange(-40.0 + x_shift, 40.1, 10.0):
            cutters.append(hex_prism(4.0, LID_T + 1.0,
                                     (float(x), float(y), LID_T / 2)))

    # M3 lid holes with a shallow counterbore for low-profile screw heads.
    for x, y in screw_boss_centers():
        cutters.append(cylinder(1.7, LID_T + SKIRT_H + 1.0,
                                (x, y, (LID_T + SKIRT_H) / 2)))
        cutters.append(cylinder(3.2, 1.25, (x, y, 0.625 - EPS)))

    return difference(lid, cutters)


def make_button():
    """Reference-derived captive plunger with an integrated LED window."""
    # Print standing on the broad outer cap. During assembly rotate it so the
    # long axis runs X through the short microSD-end wall.
    cap_t = 1.2
    stem_h = 5.0
    retainer_h = 1.0
    nose_h = BUTTON_DEPTH - cap_t - stem_h - retainer_h
    cap = rounded_box_xy(BUTTON_FACE_H, BUTTON_FACE_W, cap_t, 1.0,
                         center=(0, 0, cap_t / 2))
    stem = rounded_box_xy(4.0, 9.0, stem_h, 0.7,
                          center=(0, 0, cap_t + stem_h / 2))
    retainer = rounded_box_xy(5.0, 10.0, retainer_h, 0.8,
                              center=(0, 0, cap_t + stem_h + retainer_h / 2))
    nose = box((2.4, 3.0, nose_h),
               (0, 0, cap_t + stem_h + retainer_h + nose_h / 2))
    button = union([cap, stem, retainer, nose])
    light_window = capsule_y(BUTTON_LIGHT_LENGTH, BUTTON_LIGHT_WIDTH,
                             BUTTON_DEPTH + 1.0,
                             (0.6, POWER_LED_OFFSET_Y, BUTTON_DEPTH / 2))
    return difference(button, [light_window])


def mesh_stats(mesh):
    return {
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "body_count": int(mesh.body_count),
        "volume_mm3": round(float(mesh.volume), 2),
        "extents_mm": [round(float(v), 2) for v in mesh.extents],
        "triangles": int(len(mesh.faces)),
    }


def save_preview(base, lid_print, button, path):
    """Small dependency-light isometric raster preview using painter's sorting."""
    lid = lid_print.copy()
    # Flip from print orientation and place above base with a 10 mm exploded gap.
    lid.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
    lid.apply_translation((0, 0, BASE_H + LID_T + SKIRT_H + 10.0))
    button_view = button.copy()
    button_view.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    button_view.apply_translation((-OUT_X / 2 - 12.0, POWER_BUTTON_Y, POWER_CONTROL_Z))

    objects = [
        (base, (70, 105, 145)),
        (lid, (65, 145, 185)),
        (button_view, (230, 125, 45)),
    ]
    angle_z = math.radians(-35)
    angle_x = math.radians(-62)
    rot = (trimesh.transformations.rotation_matrix(angle_x, [1, 0, 0]) @
           trimesh.transformations.rotation_matrix(angle_z, [0, 0, 1]))

    polys = []
    all_xy = []
    for mesh, color in objects:
        verts = trimesh.transform_points(mesh.vertices, rot)
        for face in mesh.faces:
            pts = verts[face]
            normal = np.cross(pts[1] - pts[0], pts[2] - pts[0])
            if normal[2] <= 0:
                continue
            shade = 0.48 + 0.52 * abs(float(normal[2]) / (np.linalg.norm(normal) + 1e-9))
            face_color = tuple(int(min(255, c * shade)) for c in color)
            xy = pts[:, :2]
            all_xy.extend(xy.tolist())
            polys.append((float(pts[:, 2].mean()), xy, face_color))
    all_xy = np.asarray(all_xy)
    lo = all_xy.min(axis=0)
    hi = all_xy.max(axis=0)
    scale = min(980 / (hi[0] - lo[0]), 700 / (hi[1] - lo[1]))

    image = Image.new("RGB", (1200, 850), (246, 248, 250))
    draw = ImageDraw.Draw(image)
    for _, xy, color in sorted(polys, key=lambda p: p[0]):
        px = [((p[0] - lo[0]) * scale + 110,
               760 - (p[1] - lo[1]) * scale) for p in xy]
        draw.polygon(px, fill=color)
    draw.text((42, 34), "Raspberry Pi 5 + iUniker INV001 vented case", fill=(22, 33, 44))
    draw.text((42, 60), "Exploded preview — lid, base, native-button plunger", fill=(70, 80, 90))
    image.save(path)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    base = make_base()
    lid = make_lid_print_orientation()
    button = make_button()

    parts = {"base": base, "lid": lid, "power_button": button}
    pi_top_z = PI_UNDERSIDE_Z + PI_BOARD[2]
    stack_envelope_top_z = pi_top_z + HAT_TOP_ABOVE_PI
    report = {
        "units": "mm",
        "case_external_mm": [OUT_X, OUT_Y, BASE_H + LID_T],
        "case_internal_mm": [INNER_X, INNER_Y, BASE_H - FLOOR],
        "assumed_hat_envelope_mm": [*HAT_ENVELOPE, HAT_TOP_ABOVE_PI],
        "hardware_stack": {
            "evidence": "owner-supplied photos; caliper display off",
            "nominal_hat_standoff_mm": HAT_STANDOFF_H,
            "hat_pcb_thickness_mm": HAT_PCB_T,
            "topside_component_and_air_allowance_mm": HAT_TOPSIDE_ALLOWANCE,
            "stack_envelope_top_z_mm": round(stack_envelope_top_z, 2),
            "air_gap_to_base_rim_mm": round(BASE_H - stack_envelope_top_z, 2),
        },
        "native_controls": {
            "wall": "short microSD end",
            "power_button_center_y_mm": POWER_BUTTON_Y,
            "status_led_window_center_y_mm": POWER_BUTTON_Y + POWER_LED_OFFSET_Y,
            "center_z_mm": POWER_CONTROL_Z,
            "reference_button_envelope_mm": [BUTTON_FACE_W, BUTTON_DEPTH, BUTTON_FACE_H],
            "micro_sd_cutout": False,
            "fit_note": "component positions are approximate; verify with physical board",
        },
        "pi_board_origin_x_mm": PI_LEFT_X,
        "parts": {},
    }

    for name, mesh in parts.items():
        mesh.remove_unreferenced_vertices()
        mesh.fix_normals()
        path = OUT_DIR / f"pi5_iuniker_case_{name}.stl"
        mesh.export(path)
        report["parts"][name] = mesh_stats(mesh)
        if not mesh.is_watertight or mesh.volume <= 0:
            raise RuntimeError(f"{name} failed mesh validation: {report['parts'][name]}")

    # Colored, exploded GLB for convenient inspection.
    scene = trimesh.Scene()
    base_preview = base.copy()
    base_preview.visual.face_colors = [70, 105, 145, 255]
    scene.add_geometry(base_preview, node_name="base")
    lid_preview = lid.copy()
    lid_preview.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
    lid_preview.apply_translation((0, 0, BASE_H + LID_T + SKIRT_H + 10.0))
    lid_preview.visual.face_colors = [65, 145, 185, 255]
    scene.add_geometry(lid_preview, node_name="lid_exploded")
    button_preview = button.copy()
    button_preview.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    button_preview.apply_translation((-OUT_X / 2 - 12.0, POWER_BUTTON_Y, POWER_CONTROL_Z))
    button_preview.visual.face_colors = [230, 125, 45, 255]
    scene.add_geometry(button_preview, node_name="power_button")
    scene.export(OUT_DIR / "pi5_iuniker_case_assembly.glb")

    save_preview(base, lid, button, OUT_DIR / "pi5_iuniker_case_preview.png")
    (OUT_DIR / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
