from __future__ import annotations

import time

import pytest

from geomwright.studio.registry import get_module, list_modules, managed_pulley_plan, preview_module


def test_registry_exposes_schema_driven_managed_belt_modules() -> None:
    modules = list_modules()

    assert [item["kind"] for item in modules] == ["v_belt", "poly_v", "flat_belt"]
    assert all(item["capabilities"] == {"preview": True, "build": True, "inspect": False} for item in modules)
    for kind in ("v_belt", "poly_v", "flat_belt"):
        module = get_module(kind)
        spec = module.spec()
        validated = module.request_model.model_validate(spec["defaults"])

        assert spec["module"]["preview_url"] == f"/modules/{kind}/preview"
        assert spec["module"]["cad_plan_url"] == f"/modules/{kind}/cad/plan"
        assert spec["module"]["cad_job_url"] == f"/modules/{kind}/cad/jobs"
        assert spec["schema"]["additionalProperties"] is False
        assert validated.model_dump(exclude_none=True) == spec["defaults"]


def test_registry_adapts_both_belt_previews_to_one_canvas_contract() -> None:
    v_belt = preview_module("v_belt", get_module("v_belt").defaults)
    poly_v = preview_module("poly_v", get_module("poly_v").defaults)

    assert v_belt["ok"] is True
    assert v_belt["family"] == "v_belt"
    assert len(v_belt["closed_points"]) == 2
    assert len(v_belt["feature_paths"]) == 2
    assert all(path[0] != path[-1] for path in v_belt["feature_paths"])
    assert len(v_belt["guide_paths"]) == 3
    assert v_belt["summary"]["datum_diameter_mm"] == pytest.approx(100.0)
    assert [item["key"] for item in v_belt["dimensions"]] == [
        "face_width",
        "groove_pitch",
        "groove_depth",
        "groove_top_width",
        "groove_angle",
        "outer_diameter",
        "datum_diameter",
        "root_diameter",
    ]
    assert v_belt["reference_paths"][0]["key"] == "datum_diameter"
    v_dimensions = {item["key"]: item for item in v_belt["dimensions"]}
    assert v_dimensions["groove_angle"]["orientation"] == "angular"
    assert v_dimensions["groove_angle"]["vertex"] != v_dimensions["groove_angle"]["left_ray"]
    assert v_dimensions["datum_diameter"]["placement"] == "left"
    assert v_dimensions["outer_diameter"]["placement"] == "right"
    assert v_dimensions["outer_diameter"]["level"] > v_dimensions["root_diameter"]["level"]
    assert v_dimensions["root_diameter"]["target_x"] is not None
    assert v_dimensions["face_width"]["level"] > v_dimensions["groove_top_width"]["level"]
    assert [item["code"] for item in v_belt["warning_items"]] == [
        "v_belt_flat_preview",
        "licensed_standard_check",
    ]
    assert v_belt["surface_features"] == []
    assert v_belt["summary"]["top_edge_fillet_radius_mm"] is None

    assert poly_v["ok"] is True
    assert poly_v["family"] == "poly_v"
    assert len(poly_v["closed_points"]) == 1
    assert len(poly_v["feature_paths"]) == 6
    assert all(path[0] != path[-1] for path in poly_v["feature_paths"])
    assert len(poly_v["guide_paths"]) == 2
    assert poly_v["summary"]["effective_diameter_mm"] == pytest.approx(80.0)
    assert [item["key"] for item in poly_v["dimensions"]] == [
        "face_width",
        "groove_pitch",
        "groove_depth",
        "groove_angle",
        "outer_diameter",
        "effective_diameter",
        "root_diameter",
        "transition_radius",
        "maximum_root_radius",
    ]
    assert poly_v["reference_paths"][0]["key"] == "effective_diameter"
    poly_dimensions = {item["key"]: item for item in poly_v["dimensions"]}
    assert poly_dimensions["groove_angle"]["orientation"] == "angular"
    assert poly_dimensions["effective_diameter"]["placement"] == "left"
    assert poly_dimensions["transition_radius"]["orientation"] == "radius"
    assert poly_dimensions["transition_radius"]["value"] == pytest.approx(0.3)
    assert poly_dimensions["maximum_root_radius"]["value"] == pytest.approx(0.4)
    assert poly_dimensions["maximum_root_radius"]["extension_length"] > 0
    assert poly_dimensions["root_diameter"]["target_x"] is not None
    assert poly_dimensions["outer_diameter"]["level"] > poly_dimensions["root_diameter"]["level"]
    assert "editable_profile" not in poly_v
    assert v_belt["editable_profile"]["groove_angle_degrees"] == pytest.approx(34.0)

    for result in (v_belt, poly_v):
        assert result["bounds"]["x_min"] < result["bounds"]["x_max"]
        assert result["bounds"]["y_min"] < result["bounds"]["y_max"]
        assert len(result["phantom_bodies"]) == 1
        assert result["phantom_bodies"][0]["truncated"] is True
        assert len(result["phantom_bodies"][0]["surface"]) > 2
        assert result["phantom_bodies"][0]["inner_radius"] < result["summary"]["root_diameter_mm"] / 2.0
        assert result["module"]["capabilities"]["build"] is True


def test_managed_pulley_plan_owns_a_new_blank_and_internal_target_contract() -> None:
    v_plan = managed_pulley_plan("v_belt", get_module("v_belt").defaults)
    poly_plan = managed_pulley_plan("poly_v", get_module("poly_v").defaults)

    for plan in (v_plan, poly_plan):
        assert plan["stage"] == "managed_pulley_plan"
        assert plan["blank"]["scenario"] == "stepped_shaft"
        assert plan["blank"]["params"]["close_after_save"] is False
        assert plan["target"]["axial_min"] == 0.0
        assert plan["target"]["axial_max"] == pytest.approx(plan["profile_preview"]["derived"]["face_width"])
        assert plan["target"]["parameter_base"] == {
            "outer_radius_variable": "PULLEY_D1/2",
            "face_width_variable": "PULLEY_L1",
        }
        assert plan["ownership"]["schema"] == "geomwright.managed_pulley"
        assert plan["ownership"]["required_variables"] == ["PULLEY_D1", "PULLEY_L1"]
        assert "document_id" not in plan

    assert v_plan["grooves"]["axial_center"] == pytest.approx(v_plan["target"]["axial_max"] / 2.0)
    assert poly_plan["grooves"]["axial_center"] == pytest.approx(poly_plan["target"]["axial_max"] / 2.0)


def test_flat_belt_pulley_preview_and_managed_plan_cover_both_rim_profiles() -> None:
    cylindrical = preview_module("flat_belt", get_module("flat_belt").defaults)
    crowned_request = {
        "outer_diameter": 160.0,
        "face_width": 50.0,
        "crown_height": 1.5,
    }
    crowned = preview_module("flat_belt", crowned_request)

    assert cylindrical["family"] == "flat_belt"
    assert cylindrical["summary"]["edge_diameter_mm"] == pytest.approx(160.0)
    assert cylindrical["warnings"] == []
    assert crowned["summary"]["edge_diameter_mm"] == pytest.approx(157.0)
    assert crowned["summary"]["crown_radius_mm"] == pytest.approx(209.08333333333334)
    assert crowned["feature_paths"] == [crowned["guide_paths"][0]]
    assert crowned["feature_paths"][0][0][1] > 0.0
    assert crowned["feature_paths"][0][-1][1] > 0.0
    assert crowned["phantom_bodies"][0]["surface"] == crowned["feature_paths"][0]
    assert len(crowned["closed_points"][0]) > 20
    assert crowned["closed_points"][0][len(crowned["closed_points"][0]) // 2][1] > crowned["summary"]["edge_diameter_mm"] / 2.0
    assert [item["key"] for item in crowned["dimensions"]] == [
        "face_width",
        "outer_diameter",
        "crown_height",
    ]
    assert crowned["warning_items"][0]["code"] == "explicit_nonstandard_crown"
    diameter_dimensions = [item for item in crowned["dimensions"] if item["orientation"] == "diameter"]
    assert [item["symbol"] for item in diameter_dimensions] == ["⌀D"]
    assert all(item.get("start") and item.get("end") for item in diameter_dimensions)

    plan = managed_pulley_plan("flat_belt", crowned_request)
    assert plan["family"] == "flat_belt"
    assert plan["member"]["stage"] == "flat_belt_pulley_cad_plan"
    assert plan["member"]["operation"] == "boss_rotation"
    assert plan["ownership"]["required_variables"] == [
        "PULLEY_D1",
        "PULLEY_L1",
        "FP_OR",
        "FP_CROWN",
        "FP_PROFILE",
    ]
    entities = plan["member"]["bridge_preview"]["operations"][1]["profile_entities"]
    assert [item["kind"] for item in entities] == ["line", "line", "arc", "line"]
    assert entities[2]["direction"] is False
    params = plan["member"]["params"]
    assert params["require_parameterization"] is True
    assert params["require_fully_defined"] is True
    assert params["sketch"]["expected_dimension_count"] == 3
    assert {item["variable_name"] for item in params["dimensions"]} == {"PULLEY_L1", "FP_CENTER_Y", "FP_ARC_R"}
    variables = {item["name"]: item for item in plan["member"]["params"]["variables"]}
    assert variables["FP_OR"]["expression"] == "PULLEY_D1/2"
    assert variables["FP_ARC_R"]["expression"] == "(PULLEY_L1^2/4 + FP_CROWN^2)/(2*FP_CROWN)"
    assert variables["FP_CENTER_Y"]["expression"] == "FP_ARC_R - FP_OR"


def test_flat_belt_pulley_infers_profile_from_crown_height_and_rejects_impossible_crown() -> None:
    spec = get_module("flat_belt").spec()
    assert "profile" not in spec["schema"]["properties"]
    assert "profile" not in spec["defaults"]
    assert preview_module("flat_belt", {**spec["defaults"], "crown_height": 0.0})["summary"]["profile"] == "cylindrical"
    assert preview_module("flat_belt", {**spec["defaults"], "crown_height": 1.0})["summary"]["profile"] == "crowned"
    assert "rim_thickness" not in spec["schema"]["properties"]
    assert "rim_thickness" not in spec["defaults"]
    with pytest.raises(ValueError, match="positive edge radius"):
        preview_module(
            "flat_belt",
            {
                "outer_diameter": 40.0,
                "face_width": 20.0,
                "crown_height": 20.0,
            },
        )


def test_flat_belt_studio_russian_copy_covers_fields_help_summary_warning_and_progress() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "geomwright" / "studio" / "static" / "i18n.js").read_text(encoding="utf-8")

    expected = [
        '"module.flat_belt.name": "Плоскоременный шкив"',
        '"field.outer_diameter": "Наружный диаметр"',
        '"field.face_width": "Ширина обода"',
        '"field.crown_height": "Высота выпуклости"',
        '"field.crown_height.help": "0 — цилиндрический обод;',
        '"summary.profile": "Форма обода"',
        '"summary.crown_height_mm": "Высота выпуклости, мм"',
        '"warning.explicit_nonstandard_crown": "Выпуклость задана явно',
        '"cad.operation.create_flat_pulley_sketch": "Создание эскиза плоскоременного шкива',
        '"cad.operation.create_flat_pulley_rotation": "Операция вращения обода',
    ]
    assert all(text in source for text in expected)


def test_canvas_renders_neutral_bodies_and_unfilled_feature_contours() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "geomwright" / "studio" / "static" / "canvas.js").read_text(encoding="utf-8")

    assert 'context.fillStyle = "rgba(132, 174, 204, 0.055)";' in source
    assert "(state.data.feature_paths || []).forEach" in source
    assert "drawPath(path, view, { stroke, lineWidth: 2.5 });" in source
    assert "drawPath(path, view, { fill, stroke });" not in source


def test_studio_cad_plan_status_reads_flat_pulley_dimensions_without_a_target() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "geomwright" / "studio" / "static" / "app.js").read_text(encoding="utf-8")

    assert "const planDimensions = cadPlanDisplayDimensions(plan);" in source
    assert "const derived = plan?.profile_preview?.derived || {};" in source
    assert "outerDiameter: derived.outer_diameter" in source
    assert "faceWidth: derived.face_width" in source
    assert "plan.target.outer_diameter" not in source


def test_studio_exposes_a_cancel_control_for_running_cad_jobs() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    template = (root / "src" / "geomwright" / "studio" / "templates" / "fields.html").read_text(encoding="utf-8")
    source = (root / "src" / "geomwright" / "studio" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="cad-cancel-button"' in template
    assert 'requestJson(`/cad/jobs/${activeCadJobId}/cancel`, { method: "POST" })' in source


def test_bundled_bridge_contains_flat_pulley_create_and_ownership_paths() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "bridge" / "kompas_bridge.py").read_text(encoding="utf-8")
    packaged = (root / "src" / "kompas_mcp" / "assets" / "bridge" / "kompas_bridge.py").read_text(encoding="utf-8")

    assert source == packaged
    assert "def _build_managed_flat_pulley(" in source
    assert 'family not in ("v_belt", "poly_v", "flat_belt")' in source
    assert '{"FP_OR", "FP_T"}.intersection(variable_names)' in source
    assert 'name.startswith(("V-belt grooves ", "Poly-V grooves ", "Flat-belt pulley "))' in source
    assert '"feature": _v_belt_object_reference(result.get("feature"), "member.functional_feature")' in source
    assert '"sketch": _v_belt_object_reference(result.get("sketch"), "member.profile_sketch")' in source


def test_shared_pulley_body_verification_calls_api5_active_document_accessor() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "bridge" / "kompas_bridge.py").read_text(encoding="utf-8")

    assert 'document5 = safe_get(_APP5, "ActiveDocument3D")' in source
    assert "if callable(document5):\n        try:\n            document5 = document5()" in source


def test_managed_pulley_update_cannot_be_interrupted_mid_transaction() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "geomwright" / "studio" / "app.py").read_text(encoding="utf-8")

    assert "studio_adapter(cancel_event, interruptible=False).update_managed_pulley(" in source


def test_flat_belt_preview_is_registered_in_the_public_tool_catalog() -> None:
    from kompas_mcp.tool_catalog import get_mcp_tool_catalog

    catalog = get_mcp_tool_catalog()
    category = next(item for item in catalog["categories"] if item["name"] == "transmission_design")
    assert "preview_flat_belt_pulley" in category["tools"]


def test_v_belt_warning_codes_follow_conditions_instead_of_list_positions() -> None:
    custom = preview_module(
        "v_belt",
        {
            "designation": "CUSTOM",
            "datum_diameter": 100.0,
            "groove_count": 1,
            "custom_profile": {
                "datum_width": 10.0,
                "datum_offset": 2.0,
                "groove_pitch": 15.0,
                "edge_distance": 8.0,
                "groove_depth": 6.0,
                "groove_angle_degrees": 40.0,
            },
        },
    )
    overridden = preview_module(
        "v_belt",
        {
            **get_module("v_belt").defaults,
            "profile_overrides": {"groove_angle_degrees": 38.0},
        },
    )

    assert [item["code"] for item in custom["warning_items"]] == [
        "v_belt_flat_preview",
        "custom_profile_unverified",
    ]
    assert [item["code"] for item in overridden["warning_items"]] == [
        "v_belt_flat_preview",
        "licensed_standard_check",
        "profile_overrides_non_catalog",
    ]


def test_gost_v_belt_preview_shows_the_post_cut_top_edge_fillets() -> None:
    preview = preview_module(
        "v_belt",
        {
            "designation": "A",
            "datum_diameter": 100.0,
            "groove_count": 2,
            "standard_system": "gost_20889_88",
        },
    )

    fillets = preview["surface_features"]
    assert len(fillets) == 4
    assert {item["side"] for item in fillets} == {"left", "right"}
    assert {item["groove_index"] for item in fillets} == {1, 2}
    assert all(item["radius"] == pytest.approx(1.0) for item in fillets)
    assert all(item["radius_source"] == "standard" for item in fillets)
    assert all(len(item["points"]) == 13 for item in fillets)
    assert preview["summary"]["top_edge_fillet_radius_mm"] == pytest.approx(1.0)
    assert preview["dimensions"][-1]["key"] == "top_edge_fillet_radius"
    assert preview["dimensions"][-1]["symbol"] == "Rₖ"
    assert preview["warning_items"][0]["code"] == "v_belt_post_cut_fillet"

    cad_plan = managed_pulley_plan(
        "v_belt",
        {
            "designation": "A",
            "datum_diameter": 100.0,
            "groove_count": 2,
            "standard_system": "gost_20889_88",
        },
    )
    assert cad_plan["grooves"]["top_edge_fillet"]["radius"] == pytest.approx(1.0)
    assert cad_plan["grooves"]["top_edge_fillet"]["expected_edge_count"] == len(fillets)

    first_left = fillets[0]
    top_tangent = first_left["points"][0]
    flank_tangent = first_left["points"][-1]
    assert top_tangent[1] == pytest.approx(preview["bounds"]["y_max"])
    assert first_left["center"][1] == pytest.approx(top_tangent[1] - first_left["radius"])
    assert flank_tangent[0] > top_tangent[0]
    assert flank_tangent[1] < top_tangent[1]
    visible_contour = preview["closed_points"][0]
    assert len(visible_contour) > 20
    assert visible_contour[0] == pytest.approx(top_tangent)
    assert visible_contour[-1] == pytest.approx(top_tangent)
    assert [-6.508911248813579, 53.3] not in visible_contour


def test_v_belt_preview_marks_an_overridden_top_edge_fillet() -> None:
    preview = preview_module(
        "v_belt",
        {
            **get_module("v_belt").defaults,
            "profile_overrides": {"standard_top_edge_radius": 0.75},
        },
    )

    assert len(preview["surface_features"]) == 4
    assert all(item["radius"] == pytest.approx(0.75) for item in preview["surface_features"])
    assert all(item["radius_source"] == "override" for item in preview["surface_features"])


def test_http_api_serves_ui_catalog_preview_and_structured_errors() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    client = TestClient(create_app())

    root = client.get("/")
    assert root.status_code == 200
    assert "Профиль ременного шкива" in root.text
    assert 'id="workspace-save-as-document"' in root.text
    assert 'id="editor-save-document"' in root.text
    assert 'id="editor-save-as-document"' in root.text
    assert 'id="cad-save-button"' not in root.text
    health = client.get("/health").json()
    assert health["product"] == "geomwright_studio"
    assert health["mode"] == "managed_cad"
    assert health["contract_version"] == 2
    assert "managed_pulley_create_job" in health["capabilities"]
    assert client.get("/modules").json()["count"] == 3

    spec = client.get("/modules/poly_v/spec")
    assert spec.status_code == 200
    assert spec.json()["defaults"]["designation"] == "PJ"

    preview = client.post("/modules/poly_v/preview", json=spec.json()["defaults"])
    assert preview.status_code == 200
    assert preview.json()["family"] == "poly_v"
    assert len(preview.json()["closed_points"]) == 1

    cad_plan = client.post("/modules/poly_v/cad/plan", json=spec.json()["defaults"])
    assert cad_plan.status_code == 200
    assert cad_plan.json()["stage"] == "managed_pulley_plan"

    unconfirmed = client.post(
        "/modules/poly_v/cad/create",
        json={"profile": spec.json()["defaults"]},
    )
    assert unconfirmed.status_code == 409

    invalid = client.post("/modules/v_belt/preview", json={"designation": "A"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["loc"] == ["datum_diameter"]
    assert client.get("/modules/missing/spec").status_code == 404
    assert client.post("/modules/poly_v/build", json={}).status_code == 404


def test_workspace_api_routes_snapshot_activation_and_file_opening() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    class WorkspaceAdapter:
        snapshots = 0
        calls: list[tuple] = []

        def studio_workspace_snapshot(self) -> dict:
            type(self).snapshots += 1
            return {
                "ok": True,
                "active_runtime_id": "@document:1",
                "documents": [
                    {
                        "document": {"runtime_id": "@document:1", "name": "Untitled", "active": True},
                        "blocks": [{"id": "block-1", "module": "poly_v", "editable": True}],
                        "operations": [],
                    }
                ],
            }

        def activate_document(self, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append(("activate", document_id, kwargs))
            return {"ok": True, "document": {"runtime_id": document_id}}

        def open_document(self, path: str, **kwargs: object) -> dict:
            return {"document": {"path": path}, "options": kwargs}

        def save_document(self, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append(("save", document_id, kwargs))
            return {"closed": True}

        def save_document_as(self, path: str, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append(("save_as", path, document_id, kwargs))
            return {"closed": True, "saved_as": path}

        def close_document(self, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append(("close", document_id, kwargs))
            return {"closed": True}

    client = TestClient(
        create_app(
            adapter_factory=WorkspaceAdapter,
            file_picker=lambda: r"C:\models\picked.m3d",
            save_file_picker=lambda suggested_name: rf"C:\models\{suggested_name}",
        )
    )
    workspace = client.get("/workspace")
    assert workspace.status_code == 200
    assert workspace.json()["documents"][0]["blocks"][0]["module"] == "poly_v"

    activated = client.post("/workspace/activate", json={"document_id": "@document:1"})
    assert activated.status_code == 200
    assert activated.json()["activated"]["document"]["runtime_id"] == "@document:1"
    assert WorkspaceAdapter.calls[-1] == ("activate", "@document:1", {"strict": True})

    opened = client.post("/workspace/open", json={"path": r"C:\models\pulley.m3d"})
    assert opened.status_code == 200
    assert opened.json()["opened"]["document"]["path"].endswith("pulley.m3d")
    selection = client.post("/workspace/pick-file")
    assert selection.status_code == 200
    assert selection.json() == {
        "ok": True,
        "cancelled": False,
        "path": r"C:\models\picked.m3d",
    }
    picked = client.post("/workspace/open-dialog")
    assert picked.status_code == 200
    assert picked.json()["opened"]["document"]["path"].endswith("picked.m3d")
    save_selection = client.post(
        "/workspace/pick-save-file",
        json={"suggested_name": "Untitled"},
    )
    assert save_selection.json()["path"].endswith("Untitled.m3d")

    closed = client.post(
        "/workspace/close",
        json={"document_id": "@document:1", "action": "discard"},
    )
    assert closed.status_code == 200
    assert WorkspaceAdapter.calls[-1] == (
        "close",
        "@document:1",
        {"save": False, "close_mode": 0, "strict": True},
    )
    saved_as = client.post(
        "/workspace/close",
        json={
            "document_id": "@document:1",
            "action": "save",
            "save_path": r"C:\models\Untitled.m3d",
        },
    )
    assert saved_as.status_code == 200
    assert WorkspaceAdapter.calls[-1][0] == "save_as"
    assert WorkspaceAdapter.calls[-1][-1] == {"close_after_save": True, "strict": True}
    saved_copy = client.post(
        "/workspace/save-as",
        json={"document_id": "@document:1", "save_path": r"C:\models\copy.m3d"},
    )
    assert saved_copy.status_code == 200
    assert WorkspaceAdapter.calls[-1] == (
        "save_as",
        r"C:\models\copy.m3d",
        "@document:1",
        {"close_after_save": False, "strict": True},
    )
    assert client.post("/workspace/save-as", json={"document_id": "@document:1"}).status_code == 422
    assert client.post(
        "/workspace/close",
        json={"document_id": "stale", "action": "discard"},
    ).status_code == 502
    assert client.post("/workspace/open", json={}).status_code == 422


def test_workspace_reports_disconnected_state_without_failing_initialization() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    class DisconnectedAdapter:
        def studio_workspace_snapshot(self) -> dict:
            raise RuntimeError("No running visible KOMPAS-3D instance. Start KOMPAS-3D.")

    response = TestClient(create_app(adapter_factory=DisconnectedAdapter)).get("/workspace")

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "connected": False,
        "documents": [],
        "active_runtime_id": None,
        "diagnostic": "No running visible KOMPAS-3D instance. Start KOMPAS-3D.",
    }


def test_studio_marks_bridge_runner_as_visible_session_only() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    class Runner:
        require_visible_kompas = False

    class VisibleAdapter:
        runner = Runner()

        def studio_workspace_snapshot(self) -> dict:
            return {"ok": True, "connected": True, "documents": [], "active_runtime_id": None}

    response = TestClient(create_app(adapter_factory=VisibleAdapter)).get("/workspace")

    assert response.status_code == 200
    assert VisibleAdapter.runner.require_visible_kompas is True


def test_workspace_save_keeps_document_open_and_refreshes_snapshot() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    class SaveAdapter:
        calls: list[tuple] = []

        def studio_workspace_snapshot(self) -> dict:
            return {
                "ok": True,
                "active_runtime_id": "@document:0",
                "documents": [{"document": {"runtime_id": "@document:0", "name": "Untitled", "path": ""}}],
            }

        def save_document_as(self, path: str, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append((path, document_id, kwargs))
            return {"document": {"runtime_id": path, "path": path}, "closed": False}

    client = TestClient(create_app(adapter_factory=SaveAdapter))
    response = client.post(
        "/workspace/save",
        json={"document_id": "@document:0", "save_path": r"C:\models\pulley.m3d"},
    )
    assert response.status_code == 200
    assert SaveAdapter.calls == [
        (r"C:\models\pulley.m3d", "@document:0", {"close_after_save": False, "strict": True})
    ]


def test_workspace_close_saved_document_uses_strict_save_and_close() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    class SavedWorkspaceAdapter:
        calls: list[tuple] = []

        def studio_workspace_snapshot(self) -> dict:
            return {
                "ok": True,
                "active_runtime_id": r"C:\models\pulley.m3d",
                "documents": [
                    {
                        "document": {
                            "runtime_id": r"C:\models\pulley.m3d",
                            "name": "pulley.m3d",
                            "path": r"C:\models\pulley.m3d",
                            "active": True,
                        },
                        "blocks": [],
                        "operations": [],
                    }
                ],
            }

        def save_document(self, document_id: str, **kwargs: object) -> dict:
            type(self).calls.append((document_id, kwargs))
            return {"closed": True}

    client = TestClient(create_app(adapter_factory=SavedWorkspaceAdapter))
    response = client.post(
        "/workspace/close",
        json={"document_id": r"C:\models\pulley.m3d", "action": "save"},
    )

    assert response.status_code == 200
    assert SavedWorkspaceAdapter.calls == [
        (r"C:\models\pulley.m3d", {"close_after_save": True, "strict": True})
    ]


def test_cad_job_reports_real_lifecycle_without_blocking_start_request() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    calls: list[dict] = []

    class FakeAdapter:
        def create_managed_pulley(self, **kwargs: object) -> dict:
            calls.append(dict(kwargs))
            progress_callback = kwargs.get("progress_callback")
            assert callable(progress_callback)
            progress_callback(
                {
                    "percent": 50,
                    "operation": "create_groove_sketch",
                    "name": "Poly-V grooves PJ x4 profile",
                }
            )
            time.sleep(0.03)
            return {"ok": True, "stage": "executed", "verification": {"ok": True}}

    client = TestClient(create_app(adapter_factory=FakeAdapter))
    profile = get_module("poly_v").defaults
    started = client.post(
        "/modules/poly_v/cad/jobs",
        json={"profile": profile, "confirm_write": True},
    )
    assert started.status_code == 202
    job = started.json()
    assert job["status"] in {"queued", "running"}

    deadline = time.monotonic() + 1.0
    while job["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
        time.sleep(0.01)
        job = client.get(f"/cad/jobs/{job['id']}").json()

    assert job["status"] == "completed"
    assert job["stage"] == "verified"
    assert job["result"]["verification"]["ok"] is True
    assert job["progress"]["percent"] == 100
    assert job["progress"]["operation"] == "completed"
    assert calls[0]["family"] == "poly_v"
    assert calls[0]["confirm_write"] is True
    assert client.get("/cad/jobs/missing").status_code == 404
    assert client.post("/modules/poly_v/cad/jobs", json={"profile": profile}).status_code == 409


def test_cad_update_job_targets_existing_managed_block() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geomwright.studio.app import create_app

    calls: list[dict] = []

    class UpdateAdapter:
        def update_managed_pulley(self, **kwargs: object) -> dict:
            calls.append(dict(kwargs))
            progress_callback = kwargs["progress_callback"]
            progress_callback({"percent": 70, "operation": "rebuild_updated_model", "name": "Pulley"})
            return {"ok": True, "success": True, "stage": "updated"}

    client = TestClient(create_app(adapter_factory=UpdateAdapter))
    profile = get_module("poly_v").defaults
    started = client.post(
        "/modules/poly_v/cad/update-jobs",
        json={
            "profile": profile,
            "previous_profile": profile,
            "document_id": "@document:0",
            "block_id": "managed-pulley:1-2-3-4",
            "confirm_write": True,
        },
    )
    assert started.status_code == 202
    job = started.json()
    deadline = time.monotonic() + 1.0
    while job["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
        time.sleep(0.01)
        job = client.get(f"/cad/jobs/{job['id']}").json()
    assert job["status"] == "completed"
    assert calls[0]["document_id"] == "@document:0"
    assert calls[0]["block_id"] == "managed-pulley:1-2-3-4"
    assert calls[0]["previous_profile_request"] == profile
    assert calls[0]["confirm_write"] is True


def test_cli_starts_or_reopens_ui_and_reports_foreign_port_conflict(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from geomwright.studio import __main__ as ui_main

    opened: list[tuple[str, int]] = []
    monkeypatch.setattr(ui_main, "_ui_is_running", lambda _url: True)
    monkeypatch.setattr(
        ui_main.webbrowser,
        "open",
        lambda url, new: opened.append((url, new)),
    )

    ui_main.main(["--port", "9876"])
    ui_main.main(["--port", "9876", "--no-browser"])

    assert opened == [("http://127.0.0.1:9876/", 2)]
    assert "already running" in capsys.readouterr().out

    monkeypatch.setattr(ui_main, "_ui_is_running", lambda _url: False)
    monkeypatch.setattr(ui_main, "_port_is_available", lambda _port: False)
    with pytest.raises(SystemExit, match="already in use"):
        ui_main.main(["--port", "9876"])

    scheduled: list[str] = []
    uvicorn_calls: list[dict[str, object]] = []
    monkeypatch.setattr(ui_main, "_port_is_available", lambda _port: True)
    monkeypatch.setattr(ui_main, "_schedule_browser_open", scheduled.append)

    import uvicorn

    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda _app, **kwargs: uvicorn_calls.append(kwargs),
    )
    ui_main.main(["--port", "9876"])

    assert scheduled == ["http://127.0.0.1:9876/"]
    assert uvicorn_calls == [{"host": "127.0.0.1", "port": 9876, "reload": False}]


def test_cli_default_port_falls_back_for_legacy_studio_or_foreign_occupant(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from geomwright.studio import __main__ as ui_main

    monkeypatch.setattr(
        ui_main,
        "_ui_health",
        lambda _url: {
            "ok": True,
            "product": "geomwright_studio",
            "mode": "preview_only",
            "module_count": 2,
        },
    )
    assert ui_main._legacy_ui_is_running("http://127.0.0.1:8765/") is True
    assert ui_main._ui_is_running("http://127.0.0.1:8765/") is False

    monkeypatch.setattr(
        ui_main,
        "_ui_health",
        lambda _url: {
            "ok": True,
            "product": "geomwright_studio",
            "mode": "managed_cad",
            "contract_version": 2,
            "capabilities": ["managed_pulley_plan", "managed_pulley_create_job"],
            "module_count": 2,
        },
    )
    assert ui_main._ui_is_running("http://127.0.0.1:8765/") is True

    monkeypatch.setattr(ui_main, "_ui_is_running", lambda _url: False)
    monkeypatch.setattr(ui_main, "_port_is_available", lambda port: port == 8766)
    scheduled: list[str] = []
    uvicorn_calls: list[dict[str, object]] = []
    monkeypatch.setattr(ui_main, "_schedule_browser_open", scheduled.append)

    import uvicorn

    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda _app, **kwargs: uvicorn_calls.append(kwargs),
    )

    ui_main.main([])

    output = capsys.readouterr().out
    assert "older Geomwright Studio instance" in output
    assert "using 8766" in output
    assert scheduled == ["http://127.0.0.1:8766/"]
    assert uvicorn_calls == [{"host": "127.0.0.1", "port": 8766, "reload": False}]


def test_legacy_mechanics_ui_imports_remain_compatible() -> None:
    from kompas_mcp.studio.registry import list_modules as former_studio_list_modules
    from kompas_mcp.mechanics.ui.registry import list_modules as legacy_list_modules

    assert former_studio_list_modules() == list_modules()
    assert legacy_list_modules() == list_modules()
