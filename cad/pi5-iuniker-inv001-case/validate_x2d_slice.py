#!/usr/bin/env python3
"""Slice-check all case parts with Bambu Studio's X2D PETG Basic profiles.

The Bambu Studio CLI does not resolve factory-profile inheritance when passed raw
JSON files. This script resolves the bundled profile graph first, adds the case's
functional-strength overrides, slices in a temporary folder, verifies the G-code
metadata, and retains only a compact validation report (never printer G-code).
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
BAMBU = Path("/Applications/BambuStudio.app/Contents/MacOS/BambuStudio")
PROFILE_ROOT = Path("/Applications/BambuStudio.app/Contents/Resources/profiles/BBL")

MACHINE_NAME = "Bambu Lab X2D 0.4 nozzle"
PROCESS_NAME = "0.20mm Standard @BBL X2D"
FILAMENT_NAME = "Bambu PETG Basic @BBL X2D 0.4 nozzle"


def profile_index(family: str):
    result = {}
    for path in (PROFILE_ROOT / family).glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        name = data.get("name")
        if name:
            result[name] = (path, data)
    return result


def resolved_profile(family: str, name: str):
    index = profile_index(family)
    resolving = set()

    def resolve(current):
        if current in resolving:
            raise RuntimeError(f"profile inheritance cycle at {current}")
        if current not in index:
            raise KeyError(f"missing {family} profile: {current}")
        resolving.add(current)
        _, data = index[current]
        merged = {}
        parent = data.get("inherits")
        if parent:
            merged.update(resolve(parent))
        for included in data.get("include", []):
            merged.update(resolve(included))
        merged.update({k: v for k, v in data.items() if k not in ("inherits", "include")})
        resolving.remove(current)
        return merged

    profile = resolve(name)
    profile["name"] = name
    # Keep system provenance so Bambu's compatibility gate accepts the resolved
    # temporary copy as the same factory profile family.
    profile["from"] = "system"
    profile["instantiation"] = "true"
    return profile


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def gcode_setting(text, key):
    match = re.search(rf"^; {re.escape(key)} = (.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def main():
    if not BAMBU.exists():
        raise SystemExit("Bambu Studio is not installed in /Applications")

    machine = resolved_profile("machine", MACHINE_NAME)
    process = resolved_profile("process", PROCESS_NAME)
    filament = resolved_profile("filament", FILAMENT_NAME)

    # Functional-part overrides, all deliberately independent of temperature,
    # flow, retraction, and cooling maintained by Bambu's filament profile.
    process.update({
        "wall_loops": "4",
        "top_shell_layers": "5",
        "bottom_shell_layers": "5",
        "sparse_infill_density": "25%",
        "sparse_infill_pattern": "gyroid",
        "enable_support": "0",
        "elefant_foot_compensation": "0.15",
        "curr_bed_type": "Textured PEI Plate",
    })

    stls = [OUT / f"pi5_iuniker_case_{name}.stl"
            for name in ("base", "lid", "power_button")]
    missing = [str(path) for path in stls if not path.exists()]
    if missing:
        raise SystemExit(f"missing generated STL files: {missing}")

    with tempfile.TemporaryDirectory(prefix="pi5-x2d-slice-") as tmp_name:
        tmp = Path(tmp_name)
        datadir = tmp / "data"
        sliced = tmp / "slice"
        datadir.mkdir()
        sliced.mkdir()
        machine_path = tmp / "machine.json"
        process_path = tmp / "process.json"
        filament_path = tmp / "filament.json"
        write_json(machine_path, machine)
        write_json(process_path, process)
        write_json(filament_path, filament)

        command = [
            str(BAMBU), "--debug", "3", "--skip-useless-pick=1",
            "--datadir", str(datadir),
            "--load-settings", f"{machine_path};{process_path}",
            "--load-filaments", str(filament_path),
            "--load-filament-ids", "1,1,1",
            "--arrange", "1", "--ensure-on-bed", "--slice", "0",
            "--outputdir", str(sliced), *map(str, stls),
        ]
        completed = subprocess.run(command, text=True, capture_output=True)
        if completed.returncode:
            raise RuntimeError(completed.stdout + completed.stderr)

        logs = completed.stdout + completed.stderr
        result = json.loads((sliced / "result.json").read_text())
        gcode = (sliced / "plate_1.gcode").read_text(errors="replace")

        settings = {key: gcode_setting(gcode, key) for key in (
            "printer_model", "printer_settings_id", "print_settings_id",
            "filament_settings_id", "filament_type", "layer_height",
            "initial_extruder", "initial_no_support_extruder",
            "nozzle_temperature", "nozzle_temperature_initial_layer",
            "textured_plate_temp", "wall_loops", "top_shell_layers",
            "bottom_shell_layers", "sparse_infill_density",
            "sparse_infill_pattern", "enable_support",
            "elefant_foot_compensation",
        )}

        expected = {
            "printer_model": "Bambu Lab X2D",
            "filament_type": "PETG",
            "layer_height": "0.2",
            "wall_loops": "4",
            "top_shell_layers": "5",
            "bottom_shell_layers": "5",
            "sparse_infill_density": "25%",
            "sparse_infill_pattern": "gyroid",
            "enable_support": "0",
            "elefant_foot_compensation": "0.15",
        }
        mismatches = {k: {"expected": v, "actual": settings.get(k)}
                      for k, v in expected.items() if settings.get(k) != v}
        support_features = len(re.findall(
            r"^; FEATURE: (?:Support|Support interface)$", gcode, re.MULTILINE))
        if mismatches or support_features:
            raise RuntimeError(
                f"slice validation failed: mismatches={mismatches}, "
                f"support_features={support_features}"
            )

        plate = result["sliced_plates"][0]
        total_seconds = round(plate["total_predication"], 2)
        whole_seconds = round(total_seconds)
        hours, remainder = divmod(whole_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        # X2D's factory process maps the selected Standard variant to extruder 1
        # (the left/main hotend). Every object is explicitly assigned filament 1,
        # and the completed slice must contain no filament/tool changes.
        main_only = (
            process.get("print_extruder_id", [None])[0] == "1" and
            plate["filament_change_times"] == 0
        )
        if not main_only:
            nozzle_lines = "\n".join(
                line for line in logs.splitlines()
                if "nozzle_stats_obj" in line or "extruder[" in line
            )
            raise RuntimeError(
                "slice did not verify exclusive left/main nozzle use: "
                f"initial_extruder={settings.get('initial_extruder')}, "
                f"initial_no_support_extruder={settings.get('initial_no_support_extruder')}, "
                f"changes={plate['filament_change_times']}\n{nozzle_lines}"
            )

        report = {
            "status": "passed",
            "bambu_studio_cli": "02.08.02.61",
            "printer_profile": MACHINE_NAME,
            "process_profile": PROCESS_NAME,
            "filament_profile": FILAMENT_NAME,
            "left_main_nozzle_only": main_only,
            "filament_change_times": plate["filament_change_times"],
            "support_features": support_features,
            "estimated_print_time_seconds": total_seconds,
            "estimated_print_time": f"{hours}h {minutes}m {seconds}s",
            "triangle_count": plate["triangle_count"],
            "object_count": len(plate["objects"]),
            "objects": plate["objects"],
            "settings": settings,
            "warning_message": plate["warning_message"],
            "gcode_retained": False,
        }
        write_json(OUT / "x2d_petg_basic_slice_validation.json", report)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
