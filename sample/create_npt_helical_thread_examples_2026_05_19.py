from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kompas_mcp.adapter import KompasAdapter
from kompas_mcp.thread_profile_geometry import resolve_thread_profile_geometry


OUTPUT_DIR = ROOT / "sample" / "generated" / "npt_helical_thread_examples_contract_checked_2026_05_19"
CONFIG_DIR = OUTPUT_DIR / "configs"


def _set_output_dir(path: Path) -> None:
    global OUTPUT_DIR, CONFIG_DIR
    OUTPUT_DIR = path
    CONFIG_DIR = OUTPUT_DIR / "configs"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create NPT helical-thread visual examples.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory for generated .m3d files; it must not already exist.",
    )
    return parser.parse_args()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    return slug or "thread"


def _geometry(designation: str) -> dict[str, Any]:
    return dict(resolve_thread_profile_geometry({"designation": designation})["geometry"])


def _external_payload(name: str, *, designation: str, length: float, direction: str = "right") -> dict[str, Any]:
    geometry = _geometry(designation)
    major_diameter = float(geometry["major_diameter"])
    pitch = float(geometry["pitch"])
    end_diameter = major_diameter - length * float(geometry["taper_diameter_ratio"])
    shoulder_diameter = round(max(major_diameter + 12.0, major_diameter * 1.45), 3)
    shoulder_length = round(max(10.0, pitch * 5.0), 3)
    slug = _slugify(name)
    return {
        "name": name,
        "scenario": "external_helical_thread",
        "output_name": f"{slug}.m3d",
        "params": {
            "name": f"NPT external {designation} {direction}",
            "designation": designation,
            "length": length,
            "direction": direction,
            "auxiliary_geometry_hidden": True,
            "source_scenario": "external_conical_step",
            "source_params": {
                "name": f"Carrier external {designation}",
                "length": round(length + pitch * 3.0, 3),
                "start_diameter": round(major_diameter, 3),
                "end_diameter": round(end_diameter - pitch * 3.0 * float(geometry["taper_diameter_ratio"]), 3),
                "slope_direction": "inward",
                "source_scenario": "stepped_shaft",
                "source_params": {
                    "steps": [
                        {"length": round(length + pitch * 3.0 + shoulder_length, 3), "diameter": shoulder_diameter}
                    ]
                },
            },
        },
    }


def _internal_payload(name: str, *, designation: str, length: float, direction: str = "right") -> dict[str, Any]:
    geometry = _geometry(designation)
    pitch = float(geometry["pitch"])
    major_diameter = float(geometry["major_diameter"])
    minor_diameter = float(geometry["internal_minor_diameter"])
    taper = float(geometry["taper_diameter_ratio"])
    carrier_length = length + pitch * 3.0
    outer_diameter = round(max(major_diameter + 18.0, major_diameter * 1.8), 3)
    slug = _slugify(name)
    return {
        "name": name,
        "scenario": "internal_helical_thread",
        "output_name": f"{slug}.m3d",
        "params": {
            "name": f"NPT internal {designation} {direction}",
            "designation": designation,
            "length": length,
            "direction": direction,
            "auxiliary_geometry_hidden": True,
            "source_scenario": "internal_conical_step",
            "source_params": {
                "name": f"Carrier internal {designation}",
                "length": round(carrier_length, 3),
                "start_diameter": round(minor_diameter, 3),
                "end_diameter": round(minor_diameter - carrier_length * taper, 3),
                "slope_direction": "inward",
                "source_scenario": "stepped_shaft",
                "source_params": {
                    "steps": [{"length": round(carrier_length + pitch * 2.0, 3), "diameter": outer_diameter}],
                },
            },
        },
    }


EXAMPLES = [
    _external_payload("ext_1_4_18_npt_right", designation="1/4-18 NPT", length=18.0, direction="right"),
    _internal_payload("int_1_2_14_npt_right", designation="1/2-14 NPT", length=18.0, direction="right"),
]


def _ensure_new_output_directory() -> None:
    if OUTPUT_DIR.exists():
        raise RuntimeError(f"Output directory already exists: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    CONFIG_DIR.mkdir(parents=True, exist_ok=False)


def _write_config(payload: dict[str, Any]) -> Path:
    config_path = CONFIG_DIR / payload["output_name"].replace(".m3d", ".json")
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return config_path


def _create_example(adapter: KompasAdapter, payload: dict[str, Any]) -> dict[str, Any]:
    output_path = OUTPUT_DIR / payload["output_name"]
    result = adapter.create_part_from_scenario(
        payload["scenario"],
        payload["params"],
        output_path=str(output_path),
        visible=False,
        close_after_save=True,
    )
    preview = result.get("preview") or {}
    summary = preview.get("summary") or {}
    params = preview.get("params") or {}
    thread_geometry = dict(params.get("thread_geometry") or summary.get("thread_geometry") or {})
    hide_step = next(
        (step for step in result.get("steps", []) if step.get("step") == "hide_helical_thread_auxiliary_geometry"),
        {},
    )
    hidden_objects = list(hide_step.get("objects") or [])
    pitch = float(summary.get("pitch") or thread_geometry.get("pitch") or 0.0)
    length = float(summary.get("length") or params.get("length") or 0.0)
    spiral_step = next((step for step in result.get("steps", []) if step.get("step") == "create_spiral_path"), {})
    profile_parameterization_steps = [
        step
        for step in result.get("steps", [])
        if step.get("step") == "sketch_parameterization"
        and int((step.get("constraints") or {}).get("planned_count") or 0) >= 20
    ]
    profile_parameterization = profile_parameterization_steps[-1] if profile_parameterization_steps else {}
    public_variable_names = {
        str(name)
        for name in (params.get("public_profile_variables") or [])
        if str(name or "").strip()
    }
    public_variable_items = []
    for step in result.get("steps", []):
        if step.get("step") != "part_variables":
            continue
        for applied in step.get("applied") or []:
            if str(applied.get("name") or "") in public_variable_names:
                public_variable_items.append(applied)
    profile_constraint_report = profile_parameterization.get("constraints") or {}
    failed_profile_constraints = list(profile_constraint_report.get("failed") or [])
    profile_operation = next(
        (operation for operation in preview.get("operations", []) if operation.get("operation") == "create_thread_profile"),
        {},
    )
    return {
        "name": payload["name"],
        "scenario": payload["scenario"],
        "ok": bool(result.get("ok")),
        "saved": bool(result.get("saved")),
        "output_path": str(output_path),
        "config_path": str(_write_config(payload)),
        "thread_designation": summary.get("thread_designation") or params.get("designation"),
        "profile_family": params.get("thread_profile_family"),
        "thread_series": params.get("thread_series"),
        "source_units": params.get("thread_source_units"),
        "resolved_from": params.get("thread_profile_resolved_from"),
        "carrier_shape": params.get("carrier_shape"),
        "carrier_taper": params.get("carrier_taper"),
        "major_diameter_mm": summary.get("diameter"),
        "end_diameter_mm": summary.get("end_diameter"),
        "thread_reference_diameter_mm": summary.get("thread_reference_diameter"),
        "end_thread_reference_diameter_mm": summary.get("end_thread_reference_diameter"),
        "pitch_mm": pitch,
        "major_diameter_inch": thread_geometry.get("major_diameter_inch"),
        "tpi": thread_geometry.get("tpi"),
        "length_mm": length,
        "turn_count": length / pitch if pitch else None,
        "direction": summary.get("direction"),
        "profile_root_shape": params.get("profile_root_shape") or thread_geometry.get("profile_root_shape"),
        "profile_verification": profile_operation.get("verification"),
        "live_profile_parameterization": {
            "sketch_state": profile_parameterization.get("sketch_state"),
            "parameterization_order": profile_parameterization.get("parameterization_order"),
            "constraints_live_status": profile_constraint_report.get("live_status"),
            "constraints_planned_count": profile_constraint_report.get("planned_count"),
            "constraints_applied_count": profile_constraint_report.get("applied_count"),
            "constraints_failed_count": profile_constraint_report.get("failed_count"),
            "failed_constraints": failed_profile_constraints,
            "dimensions_live_status": (profile_parameterization.get("dimensions") or {}).get("live_status"),
            "dimensions_failed_count": (profile_parameterization.get("dimensions") or {}).get("failed_count"),
            "geometry_checks": profile_parameterization.get("geometry_checks"),
            "ok": bool(profile_parameterization)
            and int(profile_constraint_report.get("failed_count") or 0) == 0
            and int((profile_parameterization.get("dimensions") or {}).get("failed_count") or 0) == 0
            and bool((profile_parameterization.get("geometry_checks") or {"ok": True}).get("ok")),
        },
        "public_variable_report": {
            "expected": sorted(public_variable_names),
            "applied_count": len(public_variable_items),
            "items": public_variable_items,
            "ok": len(public_variable_items) == len(public_variable_names)
            and all(str(item.get("expression") or "").strip() not in {"", "1", "1.0"} for item in public_variable_items),
        },
        "root_flat_width_mm": thread_geometry.get("root_flat_width"),
        "auxiliary_visibility_ok": bool(hide_step.get("ok")),
        "auxiliary_hidden_count": sum(1 for item in hidden_objects if item.get("ok")),
        "spiral_carrier_shape": spiral_step.get("carrier_shape"),
        "spiral_end_carrier_diameter": spiral_step.get("end_carrier_diameter"),
    }


def _write_readme(items: list[dict[str, Any]]) -> None:
    lines = [
        "NPT tapered pipe V60 helical-thread visual examples.",
        "No zip archive is produced; open the .m3d files from this directory.",
        "Both examples use a length of several pitches so the thread has many visible turns.",
        "The NPT carrier is conical with diameter taper 1:16; the profile uses flat truncation.",
        "The sketch profile includes a verification report with horizontal/vertical dimension refs separated from tapered profile edges.",
        "",
    ]
    for item in items:
        kind = "external" if item["scenario"] == "external_helical_thread" else "internal"
        lines.append(
            "- {name}: {kind} {direction}, {designation}, start_ref={start:.3f} mm, "
            "end_ref={end:.3f} mm, P={pitch:.4f} mm, TPI={tpi:g}, length={length:.3f} mm, "
            "turns={turns:.2f}, root={root}, flat={flat:.4f} mm, saved={saved}, "
            "vars_ok={vars_ok}, profile_constraints={constraints}, aux_hidden={hidden}/6".format(
                name=Path(item["output_path"]).name,
                kind=kind,
                direction=item["direction"],
                designation=item["thread_designation"],
                start=float(item["thread_reference_diameter_mm"]),
                end=float(item["end_thread_reference_diameter_mm"]),
                pitch=float(item["pitch_mm"]),
                tpi=float(item["tpi"]),
                length=float(item["length_mm"]),
                turns=float(item["turn_count"]),
                root=item["profile_root_shape"],
                flat=float(item["root_flat_width_mm"]),
                saved=item["saved"],
                vars_ok=(item.get("public_variable_report") or {}).get("ok"),
                constraints=(item.get("live_profile_parameterization") or {}).get("constraints_live_status"),
                hidden=int(item["auxiliary_hidden_count"]),
            )
        )
    (OUTPUT_DIR / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = _parse_args()
    _set_output_dir(args.output_dir.resolve())
    _ensure_new_output_directory()
    adapter = KompasAdapter()
    items = []
    for payload in EXAMPLES:
        item = _create_example(adapter, payload)
        items.append(item)
        print(
            "{0} :: saved={1} :: {2} :: start_ref={3:.3f} mm :: end_ref={4:.3f} mm :: "
            "P={5:.4f} mm :: turns={6:.2f} :: root={7} :: aux_hidden={8}/6".format(
                Path(item["output_path"]).name,
                item["saved"],
                item["thread_designation"],
                float(item["thread_reference_diameter_mm"]),
                float(item["end_thread_reference_diameter_mm"]),
                float(item["pitch_mm"]),
                float(item["turn_count"]),
                item["profile_root_shape"],
                int(item["auxiliary_hidden_count"]),
            )
        )
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_readme(items)
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
