import importlib.util
import json
import os
from pathlib import Path

from kompas_mcp.parametric import preview_part_scenario


OUTPUT_MODEL = Path(os.environ.get("RIGHT_ORDER_OUTPUT_MODEL", "sample/live_outputs/self_wrapping_right_order_v1.m3d")).resolve()
REPORT_PATH = Path(os.environ.get("RIGHT_ORDER_REPORT_PATH", "sample/live_outputs/self_wrapping_right_order_v1_report.json"))
BRIDGE_PATH = Path(os.environ.get("RIGHT_ORDER_BRIDGE_PATH", "bridge/kompas_bridge.py")).resolve()
TURNS = float(os.environ.get("RIGHT_ORDER_TURNS", "5.0"))
SAVE_PARTIAL_ON_ERROR = os.environ.get("RIGHT_ORDER_SAVE_PARTIAL_ON_ERROR", "0") == "1"
CONSTRUCTION_ONLY = os.environ.get("RIGHT_ORDER_CONSTRUCTION_ONLY", "0") == "1"
STOP_AFTER_RIGHT_FIRST_SKETCH = os.environ.get("RIGHT_ORDER_STOP_AFTER_RIGHT_FIRST_SKETCH", "0") == "1"
STOP_AFTER_RIGHT_PROJECTED_SKETCH = os.environ.get("RIGHT_ORDER_STOP_AFTER_RIGHT_PROJECTED_SKETCH", "0") == "1"
STOP_AFTER_RIGHT_SECOND_SKETCH = os.environ.get("RIGHT_ORDER_STOP_AFTER_RIGHT_SECOND_SKETCH", "0") == "1"

KEY_NAMES = (
    "LEFT_FILLET_SPIRAL_TO_FIRST_CONTOUR",
    "SELF_WRAPPING_RIGHT_FIRST_SKETCH",
    "SELF_WRAPPING_RIGHT_SECOND_SKETCH",
    "RIGHT_FILLET_SPIRAL_TO_FIRST_CONTOUR",
    "RIGHT_FILLET_FIRST_TO_SECOND",
    "SELF_WRAPPING_RIGHT_PATH_CONTOUR",
    "EXTENSION_SPRING_PROFILE",
    "spring_body",
)


def load_bridge():
    spec = importlib.util.spec_from_file_location(
        "bridge_self_wrapping_right_order",
        BRIDGE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_named_steps(value, path="root"):
    rows = []
    if isinstance(value, dict):
        name = value.get("name") or value.get("operation") or value.get("type")
        if isinstance(name, str) and any(key in name for key in KEY_NAMES):
            rows.append(
                {
                    "path": path,
                    "name": name,
                    "valid": value.get("valid"),
                    "ok": value.get("ok"),
                    "update_ok": value.get("update_ok"),
                    "rebuild_ok": value.get("rebuild_ok"),
                    "edges_count": value.get("edges_count"),
                }
            )
        for key, child in value.items():
            rows.extend(collect_named_steps(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(collect_named_steps(child, f"{path}[{index}]"))
    return rows


def collection_rows(bridge, collection):
    rows = []
    if collection is None:
        return rows
    for index in range(bridge.collection_count(collection)):
        item = bridge.get_collection_item(collection, index)
        edges_count = None
        plane = bridge.safe_get(item, "Plane")
        coordinate_system = bridge.safe_get(item, "CoordinateSystem")
        try:
            edges_count = bridge._curve_contour_edges_count(item)
        except Exception:
            edges_count = None
        rows.append(
            {
                "index": index,
                "name": bridge.safe_get(item, "Name"),
                "reference": bridge.safe_get(item, "Reference"),
                "valid": bridge.safe_get(item, "Valid"),
                "edges_count": edges_count,
                "plane_name": bridge.safe_get(plane, "Name") if plane is not None else None,
                "plane_reference": bridge.safe_get(plane, "Reference") if plane is not None else None,
                "coordinate_system_name": bridge.safe_get(coordinate_system, "Name") if coordinate_system is not None else None,
                "coordinate_system_reference": bridge.safe_get(coordinate_system, "Reference") if coordinate_system is not None else None,
            }
        )
    return rows


def main():
    bridge = load_bridge()
    params = {
        "name": "Self Wrapping Right Order v1",
        "hook_type": "self_wrapping_hooks",
        "wire_diameter": 3.0,
        "outer_diameter": 30.0,
        "turns": TURNS,
        "gap": 1.0,
        "construction_only": CONSTRUCTION_ONLY,
        "self_wrapping_right_stop_after_first_sketch": STOP_AFTER_RIGHT_FIRST_SKETCH,
        "self_wrapping_right_stop_after_projected_sketch": STOP_AFTER_RIGHT_PROJECTED_SKETCH,
        "self_wrapping_right_stop_after_second_sketch": STOP_AFTER_RIGHT_SECOND_SKETCH,
        "output_path": str(OUTPUT_MODEL),
        "close_after_save": True,
    }
    preview = preview_part_scenario("extension_spring", params)
    preview["params"].update(
        {
            "output_path": str(OUTPUT_MODEL),
            "close_after_save": True,
            "construction_only": CONSTRUCTION_ONLY,
            "self_wrapping_right_stop_after_first_sketch": STOP_AFTER_RIGHT_FIRST_SKETCH,
            "self_wrapping_right_stop_after_projected_sketch": STOP_AFTER_RIGHT_PROJECTED_SKETCH,
            "self_wrapping_right_stop_after_second_sketch": STOP_AFTER_RIGHT_SECOND_SKETCH,
        }
    )
    try:
        result = bridge.handle_create_part_from_scenario(
            {
                "scenario": "extension_spring",
                "params": preview["params"],
                "preview": preview,
                "visible": True,
            }
        )
    except Exception as exc:
        if not SAVE_PARTIAL_ON_ERROR:
            raise
        save_report = None
        save_error = None
        readback = {}
        try:
            save_report = bridge.handle_save_document({"path": str(OUTPUT_MODEL), "close_after_save": False})
            app = bridge.make_app()
            document = bridge.resolve_document(app, (save_report.get("document") or {}).get("id"))
            part = bridge.safe_get(document, "TopPart") if document is not None else None
            model = bridge.cast_model_container(part) if part is not None else None
            aux = bridge._cast_to_com_interface(part, "IAuxiliaryGeomContainer") if part is not None else None
            readback = {
                "sketches": collection_rows(bridge, bridge._get_sketch_collection(model)) if model is not None else [],
                "fillets": collection_rows(bridge, bridge.safe_get(aux, "FilletCurves")) if aux is not None else [],
                "contours": collection_rows(bridge, bridge.safe_get(aux, "Contours3D")) if aux is not None else [],
                "evolutions": collection_rows(bridge, bridge.safe_get(model, "Evolutions")) if model is not None else [],
            }
        except Exception as save_exc:
            save_error = str(save_exc)
        report = {
            "output_model": str(OUTPUT_MODEL),
            "turns": TURNS,
            "partial_saved_on_error": True,
            "error": str(exc),
            "preview_hook_type": preview.get("params", {}).get("hook_type"),
            "save_report": save_report,
            "save_error": save_error,
            "readback": readback,
        }
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"model": str(OUTPUT_MODEL), "report": str(REPORT_PATH), "partial": True, "error": str(exc), "save_error": save_error}, ensure_ascii=False, indent=2))
        return

    reopened = bridge.handle_open_document({"path": str(OUTPUT_MODEL), "visible": True})
    app = bridge.make_app()
    document = bridge.resolve_document(app, reopened["document"]["id"])
    part = bridge.safe_get(document, "TopPart")
    model = bridge.cast_model_container(part)
    aux = bridge._cast_to_com_interface(part, "IAuxiliaryGeomContainer")

    readback = {
        "sketches": collection_rows(bridge, bridge._get_sketch_collection(model)),
        "fillets": collection_rows(bridge, bridge.safe_get(aux, "FilletCurves")),
        "contours": collection_rows(bridge, bridge.safe_get(aux, "Contours3D")),
        "evolutions": collection_rows(bridge, bridge.safe_get(model, "Evolutions")),
    }
    report = {
        "output_model": str(OUTPUT_MODEL),
        "turns": TURNS,
        "preview_hook_type": preview.get("params", {}).get("hook_type"),
        "key_order": collect_named_steps(result),
        "create_result": result,
        "reopen": reopened,
        "readback": readback,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    bridge.handle_save_document({"document_id": reopened["document"]["id"], "path": str(OUTPUT_MODEL), "close_after_save": True})
    print(json.dumps({"model": str(OUTPUT_MODEL), "report": str(REPORT_PATH), "keys": report["key_order"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
