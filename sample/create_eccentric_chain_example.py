from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from bridge.kompas_bridge import _build_stepped_shaft_feature
from bridge.kompas_bridge import _create_local_coordinate_system_on_point
from bridge.kompas_bridge import _create_part_document
from bridge.kompas_bridge import _create_point3d_center_on_object
from bridge.kompas_bridge import _create_point3d_displace
from bridge.kompas_bridge import _save_generated_part_document
from bridge.kompas_bridge import _select_far_end_planar_face
from bridge.kompas_bridge import apply_part_properties
from bridge.kompas_bridge import make_app
from kompas_mcp.parametric import preview_stepped_shaft


CONFIG_NAME = "eccentric_chain_demo.json"


def load_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    sample_path = ROOT / "sample" / CONFIG_NAME
    payload = load_payload(sample_path)

    output_dir = ROOT / "sample" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / payload["output_name"]

    app = make_app()
    doc3 = None
    steps_report: list[dict] = []

    try:
        doc3, part, model_container = _create_part_document(app, False)
        steps_report.append({"step": "create_part_document", "ok": True})

        property_report = apply_part_properties(part, payload)
        if property_report:
            steps_report.append(
                {
                    "step": "set_part_properties_initial",
                    "ok": all(item["ok"] for item in property_report),
                    "properties": property_report,
                }
            )

        primary_preview = preview_stepped_shaft(payload["primary_shaft"])
        primary_feature = _build_stepped_shaft_feature(
            part,
            model_container,
            primary_preview["params"],
            primary_preview,
            steps_report,
        )

        far_face, selector_report = _select_far_end_planar_face(primary_feature["rotated"])
        steps_report.append(
            {
                "step": "resolve_far_end_face",
                "ok": True,
                "selector_report": selector_report,
            }
        )

        center_name = payload.get("point_names", {}).get("center") or "PT_CENTER"
        center_point = _create_point3d_center_on_object(model_container, center_name, far_face)
        steps_report.append(
            {
                "step": "create_point",
                "role": "center_of_object",
                "ok": True,
                "name": center_name,
                "origin": [center_point.X, center_point.Y, center_point.Z],
                "reference": getattr(center_point, "Reference", None),
            }
        )

        offset_name = payload.get("point_names", {}).get("offset") or "PT_ECC"
        offset_point = _create_point3d_displace(model_container, offset_name, center_point, payload.get("offset") or [0, 0, 0])
        steps_report.append(
            {
                "step": "create_point",
                "role": "offset_from_point",
                "ok": True,
                "name": offset_name,
                "origin": [offset_point.X, offset_point.Y, offset_point.Z],
                "reference": getattr(offset_point, "Reference", None),
                "offset": payload.get("offset") or [0, 0, 0],
            }
        )

        lcs_name = str(payload.get("lcs_name") or "LCS_ECC")
        lcs = _create_local_coordinate_system_on_point(part, lcs_name, offset_point, rotation={})
        steps_report.append(
            {
                "step": "create_lcs",
                "ok": True,
                "name": lcs_name,
                "origin": [getattr(lcs, "X", 0.0), getattr(lcs, "Y", 0.0), getattr(lcs, "Z", 0.0)],
                "reference": getattr(lcs, "Reference", None),
            }
        )

        secondary_preview = preview_stepped_shaft(payload["secondary_shaft"])
        _build_stepped_shaft_feature(
            part,
            model_container,
            secondary_preview["params"],
            secondary_preview,
            steps_report,
            coordinate_system=lcs,
        )

        saved, _ = _save_generated_part_document(doc3, app, str(output_path), True, steps_report)
        print(
            "{0} :: saved={1} :: primary_steps={2} :: secondary_steps={3}".format(
                output_path.name,
                saved,
                len(primary_preview["params"]["steps"]),
                len(secondary_preview["params"]["steps"]),
            )
        )
    except Exception:
        if doc3 is not None:
            try:
                doc3.Close(0)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
