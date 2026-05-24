import tempfile
import unittest
from pathlib import Path

from kompas_mcp.operation_runtime import (
    DocumentReadbackContractSpec,
    OperationContractSpec,
    OperationInvariantSpec,
    OperationRegressionSpec,
    ThreadGeometryProbeSpec,
    build_diagnostic_bundle,
    build_failure_triage,
    build_human_audit_report,
    build_operation_manifest,
    build_reproducibility_snapshot,
    build_run_ledger,
    compare_run_regression,
    verify_document_readback_contract,
    verify_operation_contract,
    verify_thread_geometry_probes,
    verify_operation_result,
)


class OperationRuntimeTests(unittest.TestCase):
    def test_verify_successful_thread_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "part.m3d"
            output_path.write_bytes(b"kompas-model")
            result = {
                "ok": True,
                "saved": True,
                "steps": [
                    {"step": "create_part_document", "ok": True},
                    {"step": "hide_helical_thread_auxiliary_geometry", "ok": True, "hidden": True, "objects": [
                        {"role": "spiral_axis", "ok": True, "requested_hidden": True, "hidden_after": True},
                        {"role": "profile_sketch", "ok": True, "requested_hidden": True, "hidden_after": True},
                    ]},
                ],
                "preview": {
                    "operations": [
                        {"operation": "cut_evolution", "diameter": 12.0, "pitch": 1.0, "length": 14.0, "direction": "right"}
                    ]
                },
            }
            spec = OperationInvariantSpec(
                scenario="external_helical_thread",
                output_path=str(output_path),
                required_steps=("create_part_document", "hide_helical_thread_auxiliary_geometry"),
                require_auxiliary_hidden=True,
                expected_auxiliary_roles=("spiral_axis", "profile_sketch"),
                expected_operation_values={"cut_evolution": {"diameter": 12.0, "pitch": 1.0, "length": 14.0, "direction": "right"}},
            )

            report = verify_operation_result(result, spec)

        self.assertTrue(report.ok)
        payload = report.to_dict()
        self.assertTrue(all(check["ok"] for check in payload["checks"]))

    def test_verify_reports_auxiliary_and_geometry_failures(self) -> None:
        result = {
            "ok": True,
            "saved": True,
            "steps": [
                {"step": "hide_helical_thread_auxiliary_geometry", "ok": True, "hidden": True, "objects": [
                    {"role": "spiral_axis", "ok": True, "requested_hidden": True, "hidden_after": False},
                ]},
            ],
            "preview": {"operations": [{"operation": "cut_evolution", "diameter": 10.0}]},
        }
        spec = OperationInvariantSpec(
            scenario="external_helical_thread",
            required_steps=("create_part_document",),
            require_auxiliary_hidden=True,
            expected_auxiliary_roles=("spiral_axis", "profile_sketch"),
            expected_operation_values={"cut_evolution": {"diameter": 12.0}},
        )

        report = verify_operation_result(result, spec)
        failed = {check.name for check in report.checks if not check.ok}

        self.assertFalse(report.ok)
        self.assertIn("step:create_part_document", failed)
        self.assertIn("auxiliary_objects_hidden", failed)
        self.assertIn("auxiliary_roles", failed)
        self.assertIn("preview_operation:cut_evolution.diameter", failed)

    def test_build_operation_manifest_collects_low_level_artifacts(self) -> None:
        result = {
            "scenario": "external_helical_thread",
            "ok": True,
            "saved": True,
            "output_path": "part.m3d",
            "steps": [
                {"step": "create_part_document", "ok": True, "api": "api7_documents_add"},
                {
                    "step": "part_variables",
                    "ok": True,
                    "applied": [
                        {
                            "name": "D1",
                            "value": 12.0,
                            "expression": "12",
                            "reference": 100,
                            "update_ok": True,
                            "variable": {"name": "D1", "external": True},
                        }
                    ],
                    "applied_count": 1,
                    "failed_count": 0,
                },
                {
                    "step": "hide_helical_thread_auxiliary_geometry",
                    "ok": True,
                    "hidden": True,
                    "objects": [
                        {
                            "role": "spiral_axis",
                            "name": "Axis Thread 1",
                            "reference": 101,
                            "ok": True,
                            "requested_hidden": True,
                            "hidden_before": False,
                            "hidden_after": True,
                            "update_ok": True,
                        },
                        {
                            "role": "profile_sketch",
                            "name": "Sketch Thread 1",
                            "reference": 102,
                            "ok": True,
                            "requested_hidden": True,
                            "hidden_before": True,
                            "hidden_after": True,
                            "update_ok": True,
                        },
                    ],
                },
            ],
            "preview": {
                "operations": [
                    {"operation": "cut_evolution", "diameter": 12.0, "pitch": 1.0, "metadata": {"ignored": True}}
                ]
            },
        }

        manifest = build_operation_manifest(result)

        self.assertTrue(manifest["ok"])
        self.assertEqual(manifest["counts"]["variables"], 1)
        self.assertEqual(manifest["counts"]["operations"], 1)
        self.assertEqual(manifest["counts"]["auxiliary_objects"], 2)
        self.assertEqual(manifest["counts"]["hidden_auxiliary_objects"], 2)
        self.assertEqual(manifest["variables"][0]["name"], "D1")
        self.assertEqual(manifest["operations"][0]["operation"], "cut_evolution")
        self.assertNotIn("metadata", manifest["operations"][0])
        self.assertEqual(manifest["auxiliary_objects"][0]["kind"], "axis")
        self.assertFalse(manifest["auxiliary_objects"][0]["visible_after"])

    def test_verify_thread_geometry_probes_success(self) -> None:
        result = {
            "preview": {
                "operations": [
                    {
                        "operation": "create_source_body",
                        "summary": {"total_length": 26.0},
                        "source_diameter_validation": {"matches": True, "status": "match", "delta": 0.0},
                    },
                    {
                        "operation": "create_spiral_path",
                        "diameter": 12.0,
                        "pitch": 1.0,
                        "length": 14.0,
                        "spiral_length": 15.05,
                        "direction": "right",
                    },
                    {
                        "operation": "create_thread_profile",
                        "major_radius": 6.0,
                        "depth": 0.6134346610139776,
                        "root_diameter": 10.773130677972045,
                        "profile_angle_degrees": 60.0,
                        "profile_outer_half_width": 0.4375,
                    },
                    {
                        "operation": "cut_evolution",
                        "diameter": 12.0,
                        "pitch": 1.0,
                        "length": 14.0,
                        "spiral_length": 15.05,
                        "depth": 0.6134346610139776,
                        "direction": "right",
                        "internal": False,
                        "source_diameter_validation": {"matches": True, "status": "match", "delta": 0.0},
                    },
                ]
            }
        }

        report = verify_thread_geometry_probes(
            result,
            ThreadGeometryProbeSpec(
                diameter=12.0,
                pitch=1.0,
                length=14.0,
                depth=0.6134346610139776,
                min_source_total_length=14.0,
            ),
        )

        self.assertTrue(report.ok)

    def test_verify_thread_geometry_probes_reports_mismatch(self) -> None:
        result = {
            "preview": {
                "operations": [
                    {"operation": "create_spiral_path", "diameter": 12.0, "pitch": 1.25, "length": 14.0, "spiral_length": 15.05, "direction": "right"},
                    {"operation": "create_thread_profile", "major_radius": 6.0, "depth": 0.5, "root_diameter": 11.2, "profile_angle_degrees": 60.0, "profile_outer_half_width": 0.4375},
                    {"operation": "cut_evolution", "diameter": 12.0, "pitch": 1.25, "length": 14.0, "spiral_length": 15.05, "depth": 0.5, "direction": "right", "internal": False},
                ]
            }
        }

        report = verify_thread_geometry_probes(
            result,
            ThreadGeometryProbeSpec(diameter=12.0, pitch=1.0, length=14.0, depth=0.6134346610139776),
        )
        failed = {check.name for check in report.checks if not check.ok}

        self.assertFalse(report.ok)
        self.assertIn("spiral.pitch", failed)
        self.assertIn("profile.depth", failed)
        self.assertIn("profile.root_diameter", failed)
        self.assertIn("cut.pitch", failed)

    def test_build_diagnostic_bundle_summarizes_reports_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "part.m3d"
            output_path.write_bytes(b"kompas-model")
            report = {
                "stage": "stage_a",
                "ok": True,
                "checks": [{"name": "a", "ok": True, "expected": True, "actual": True}],
            }

            bundle = build_diagnostic_bundle(
                scenario="external_helical_thread",
                reports={"preflight": report},
                artifacts={"model": str(output_path)},
                manifest={"ok": True, "counts": {"steps": 2, "operations": 1}},
            )

        self.assertTrue(bundle["ok"])
        self.assertEqual(bundle["counts"]["sections"], 1)
        self.assertEqual(bundle["counts"]["failed_checks"], 0)
        self.assertEqual(bundle["counts"]["steps"], 2)
        self.assertEqual(bundle["artifacts"][0]["role"], "model")

    def test_build_diagnostic_bundle_reports_failures(self) -> None:
        report = {
            "stage": "stage_a",
            "ok": False,
            "checks": [{"name": "a", "ok": False, "expected": True, "actual": False}],
        }

        bundle = build_diagnostic_bundle(
            scenario="external_helical_thread",
            reports={"preflight": report},
            artifacts={"model": "missing.m3d"},
            manifest={"ok": False, "counts": {}},
        )

        self.assertFalse(bundle["ok"])
        self.assertEqual(bundle["counts"]["failed_checks"], 3)
        self.assertEqual(bundle["failures"][0]["section"], "preflight")
        self.assertEqual(bundle["failures"][1]["section"], "artifacts")
        self.assertEqual(bundle["failures"][2]["section"], "manifest")

    def test_verify_operation_contract_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "part.m3d"
            output_path.write_bytes(b"kompas-model")
            bundle = {
                "ok": True,
                "scenario": "external_helical_thread",
                "sections": [
                    {"name": "operation_invariants", "ok": True},
                    {"name": "thread_geometry_probes", "ok": True},
                ],
                "artifacts": [{"role": "model", "exists": True, "size_bytes": output_path.stat().st_size}],
            }
            manifest = {
                "ok": True,
                "counts": {"steps": 21, "operations": 8, "auxiliary_objects": 6},
                "operations": [{"operation": "create_spiral_path"}, {"operation": "cut_evolution"}],
                "variables": [{"name": "D1"}],
                "auxiliary_objects": [
                    {"role": "spiral_axis", "visible_after": False},
                    {"role": "profile_sketch", "visible_after": False},
                ],
            }

            report = verify_operation_contract(
                bundle,
                manifest,
                OperationContractSpec(
                    scenario="external_helical_thread",
                    required_sections=("operation_invariants", "thread_geometry_probes"),
                    required_artifact_roles=("model",),
                    min_counts={"steps": 20, "operations": 2, "auxiliary_objects": 2},
                    expected_operation_names=("create_spiral_path", "cut_evolution"),
                    expected_variable_names=("D1",),
                    expected_auxiliary_roles=("spiral_axis", "profile_sketch"),
                ),
            )

        self.assertTrue(report.ok)

    def test_verify_operation_contract_reports_drift(self) -> None:
        bundle = {
            "ok": True,
            "scenario": "external_helical_thread",
            "sections": [{"name": "operation_invariants", "ok": True}],
            "artifacts": [{"role": "model", "exists": False, "size_bytes": 0}],
        }
        manifest = {
            "ok": True,
            "counts": {"steps": 5, "operations": 1, "auxiliary_objects": 1},
            "operations": [{"operation": "create_spiral_path"}],
            "variables": [],
            "auxiliary_objects": [{"role": "spiral_axis", "visible_after": True}],
        }

        report = verify_operation_contract(
            bundle,
            manifest,
            OperationContractSpec(
                scenario="external_helical_thread",
                required_sections=("thread_geometry_probes",),
                required_artifact_roles=("model",),
                min_counts={"steps": 20},
                expected_operation_names=("cut_evolution",),
                expected_variable_names=("D1",),
                expected_auxiliary_roles=("spiral_axis", "profile_sketch"),
            ),
        )
        failed = {check.name for check in report.checks if not check.ok}

        self.assertFalse(report.ok)
        self.assertIn("section:thread_geometry_probes", failed)
        self.assertIn("artifact:model", failed)
        self.assertIn("count:steps", failed)
        self.assertIn("operation:cut_evolution", failed)
        self.assertIn("variable:D1", failed)
        self.assertIn("auxiliary:profile_sketch", failed)
        self.assertIn("auxiliary_contract_hidden", failed)

    def test_verify_document_readback_contract_success(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "counts": {"documents": 1, "items": 3, "tree_nodes": 3},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
            },
            DocumentReadbackContractSpec(min_items=3, min_tree_nodes=3),
        )

        self.assertTrue(report.ok)

    def test_verify_document_readback_contract_matches_expected_items(self) -> None:
        readback_report = {
            "ok": True,
            "model_path": "part.m3d",
            "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
            "counts": {"documents": 1, "items": 2, "tree_nodes": 2},
            "checks": [
                {"name": "open_document", "ok": True},
                {"name": "document_path_matches_model_name", "ok": True},
                {"name": "close_document", "ok": True},
            ],
            "failures": [],
            "readback": {
                "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                "document_tree": {
                    "tree": {
                        "id": "root",
                        "name": "Part",
                        "type": "part",
                        "children": [{"id": "sketch-1", "name": "ThreadSketch", "type": "sketch", "role": "profile_sketch"}],
                    }
                },
                    "items": {
                        "items": [
                            {
                                "id": "sketch-1",
                                "name": "ThreadSketch",
                                "type": "sketch",
                                "role": "profile_sketch",
                                "reference": 101,
                                "hidden": True,
                                "visible": False,
                            },
                            {"id": "axis-1", "name": "ThreadAxis", "type": "axis", "role": "spiral_axis", "reference": 102},
                        ]
                    },
                "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                "close_document": {"closed": True},
            },
        }

        report = verify_document_readback_contract(
            readback_report,
            DocumentReadbackContractSpec(
                expected_items=(
                    {"type": "sketch", "role": "profile_sketch", "hidden": True, "visible": False},
                    {"reference": 102, "role": "spiral_axis"},
                )
            ),
        )

        self.assertTrue(report.ok)
        self.assertIn("readback_item:role=profile_sketch", {check.name for check in report.checks})

    def test_verify_document_readback_contract_matches_expected_item_contains(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "model_path": "part.m3d",
                "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
                "counts": {"documents": 1, "items": 1, "tree_nodes": 1},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
                "failures": [],
                "readback": {
                    "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                    "document_tree": {
                        "tree": {
                            "id": "root",
                            "name": "Part",
                            "type": "part",
                            "children": [
                                {
                                    "id": "sketch-1",
                                    "name": "Thread_Profile_Sketch",
                                    "type": "ksSketchDefinition",
                                    "role": "profile_sketch",
                                    "path": "Part/Sketches/Thread_Profile_Sketch",
                                }
                            ],
                        }
                    },
                    "items": {"items": []},
                    "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                    "close_document": {"closed": True},
                },
            },
            DocumentReadbackContractSpec(
                expected_items=(
                    {
                        "name_contains": "profile",
                        "type_contains": "sketch",
                        "path_contains": "sketches/thread",
                        "parent_id": "root",
                        "depth": 1,
                        "children_count": 0,
                        "unique": True,
                    },
                )
            ),
        )

        self.assertTrue(report.ok)
        self.assertIn("readback_item:name_contains=profile", {check.name for check in report.checks})

    def test_verify_document_readback_contract_matches_expected_item_numeric_fields(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "model_path": "part.m3d",
                "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
                "counts": {"documents": 1, "items": 1, "tree_nodes": 1},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
                "failures": [],
                "readback": {
                    "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                    "document_tree": {"tree": {"id": "root", "name": "Part", "type": "part"}},
                    "items": {
                        "items": [
                            {
                                "id": "axis-1",
                                "name": "ThreadAxis",
                                "type": "axis",
                                "role": "spiral_axis",
                                "metrics": {"length": 22.001, "origin": {"x": 10.0}},
                            }
                        ]
                    },
                    "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                    "close_document": {"closed": True},
                },
            },
            DocumentReadbackContractSpec(
                expected_items=(
                    {
                        "role": "spiral_axis",
                        "numeric_fields": {
                            "metrics.length": 22.0,
                            "metrics.origin.x": {"expected": 9.99, "tolerance": 0.02},
                        },
                        "numeric_tolerance": 0.01,
                        "unique": True,
                    },
                )
            ),
        )

        self.assertTrue(report.ok)
        self.assertIn("readback_item:role=spiral_axis", {check.name for check in report.checks})

    def test_verify_document_readback_contract_matches_expected_item_custom_fields(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "model_path": "part.m3d",
                "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
                "counts": {"documents": 1, "items": 1, "tree_nodes": 1},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
                "failures": [],
                "readback": {
                    "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                    "document_tree": {"tree": {"id": "root", "name": "Part", "type": "part"}},
                    "items": {
                        "items": [
                            {
                                "id": "axis-1",
                                "name": "ThreadAxis",
                                "type": "axis",
                                "role": "spiral_axis",
                                "properties": {"layer": "Construction", "owner": "ThreadBuilder"},
                                "geometry": {"kind": "AxisLine", "tags": ["thread", "auxiliary"]},
                            }
                        ]
                    },
                    "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                    "close_document": {"closed": True},
                },
            },
            DocumentReadbackContractSpec(
                expected_items=(
                    {
                        "role": "spiral_axis",
                        "field_equals": {"properties.layer": "construction", "geometry.tags.0": "thread"},
                        "field_contains": {"properties.owner": "builder", "geometry.kind": "axis"},
                        "field_has": {"geometry.tags": ["thread", "auxiliary"]},
                        "field_has_contains": {"geometry.tags": "aux"},
                        "field_exists": ["properties.layer", "geometry.tags.1"],
                        "field_missing": ["properties.suppressed", "geometry.tags.5"],
                        "unique": True,
                    },
                )
            ),
        )

        self.assertTrue(report.ok)
        self.assertIn("readback_item:role=spiral_axis", {check.name for check in report.checks})

    def test_verify_document_readback_contract_reports_missing_required_field(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "model_path": "part.m3d",
                "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
                "counts": {"documents": 1, "items": 1, "tree_nodes": 1},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
                "failures": [],
                "readback": {
                    "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                    "document_tree": {"tree": {"id": "root", "name": "Part", "type": "part"}},
                    "items": {
                        "items": [
                            {
                                "id": "axis-1",
                                "name": "ThreadAxis",
                                "type": "axis",
                                "role": "spiral_axis",
                                "properties": {"layer": "Construction"},
                            }
                        ]
                    },
                    "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                    "close_document": {"closed": True},
                },
            },
            DocumentReadbackContractSpec(
                expected_items=(
                    {
                        "role": "spiral_axis",
                        "field_exists": ["properties.layer", "properties.owner"],
                    },
                )
            ),
        )
        failed = {check.name for check in report.checks if not check.ok}

        self.assertFalse(report.ok)
        self.assertIn("readback_item:role=spiral_axis", failed)

    def test_verify_document_readback_contract_reports_missing_expected_item(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "model_path": "part.m3d",
                "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
                "counts": {"documents": 1, "items": 1, "tree_nodes": 1},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
                "failures": [],
                "readback": {
                    "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                    "document_tree": {"tree": {"id": "root", "name": "Part", "type": "part"}},
                    "items": {"items": [{"id": "root", "name": "Part", "type": "part"}]},
                    "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                    "close_document": {"closed": True},
                },
            },
            DocumentReadbackContractSpec(expected_items=({"role": "profile_sketch"},)),
        )
        failed = {check.name for check in report.checks if not check.ok}

        self.assertFalse(report.ok)
        self.assertIn("readback_item:role=profile_sketch", failed)

    def test_verify_document_readback_contract_reports_non_unique_expected_item(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "model_path": "part.m3d",
                "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
                "counts": {"documents": 1, "items": 2, "tree_nodes": 1},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
                "failures": [],
                "readback": {
                    "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                    "document_tree": {"tree": {"id": "root", "name": "Part", "type": "part"}},
                    "items": {
                        "items": [
                            {"id": "sketch-1", "name": "ThreadSketch", "type": "sketch", "role": "profile_sketch"},
                            {"id": "sketch-2", "name": "ThreadSketch", "type": "sketch", "role": "profile_sketch"},
                        ]
                    },
                    "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                    "close_document": {"closed": True},
                },
            },
            DocumentReadbackContractSpec(expected_items=({"role": "profile_sketch", "unique": True},)),
        )
        failed = {check.name for check in report.checks if not check.ok}

        self.assertFalse(report.ok)
        self.assertIn("readback_item_max:role=profile_sketch", failed)

    def test_verify_document_readback_contract_rejects_invalid_expected_item_spec(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "model_path": "part.m3d",
                "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
                "counts": {"documents": 1, "items": 1, "tree_nodes": 1},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
                "failures": [],
                "readback": {
                    "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                    "document_tree": {"tree": {"id": "root", "name": "Part", "type": "part"}},
                    "items": {"items": [{"id": "sketch-1", "name": "ThreadSketch", "type": "sketch"}]},
                    "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                    "close_document": {"closed": True},
                },
            },
            DocumentReadbackContractSpec(
                expected_items=(
                    ["role", "profile_sketch"],
                    {"role": "profile_sketch", "min_count": "many"},
                    {"role": "profile_sketch", "min_count": -1},
                    {"role": "profile_sketch", "max_count": -1},
                    {"role": "profile_sketch", "field_equals": ["properties.layer"]},
                    {"role": "profile_sketch", "field_contains": ["properties.layer"]},
                    {"role": "profile_sketch", "field_has": ["geometry.tags"]},
                    {"role": "profile_sketch", "field_has_contains": ["geometry.tags"]},
                    {"role": "profile_sketch", "field_exists": {"properties.layer": True}},
                    {"role": "profile_sketch", "numeric_fields": ["metrics.length"]},
                    {"role": "profile_sketch", "numeric_tolerance": "wide"},
                    {"role": "profile_sketch", "numeric_fields": {"metrics.length": {"expected": 1, "tolerance": "wide"}}},
                )
            ),
        )
        failed = {check.name for check in report.checks if not check.ok}

        self.assertFalse(report.ok)
        self.assertIn("readback_item_spec:expected:0", failed)
        self.assertIn("readback_item_spec:expected:1", failed)
        self.assertIn("readback_item_spec:expected:2", failed)
        self.assertIn("readback_item_spec:expected:3", failed)
        self.assertIn("readback_item_spec:expected:4", failed)
        self.assertIn("readback_item_spec:expected:5", failed)
        self.assertIn("readback_item_spec:expected:6", failed)
        self.assertIn("readback_item_spec:expected:7", failed)
        self.assertIn("readback_item_spec:expected:8", failed)
        self.assertIn("readback_item_spec:expected:9", failed)
        self.assertIn("readback_item_spec:expected:10", failed)
        self.assertIn("readback_item_spec:expected:11", failed)

    def test_verify_document_readback_contract_accepts_forbidden_item_absence(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "model_path": "part.m3d",
                "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
                "counts": {"documents": 1, "items": 1, "tree_nodes": 1},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
                "failures": [],
                "readback": {
                    "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                    "document_tree": {"tree": {"id": "root", "name": "Part", "type": "part"}},
                    "items": {"items": [{"id": "sketch-1", "name": "ThreadSketch", "type": "sketch"}]},
                    "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                    "close_document": {"closed": True},
                },
            },
            DocumentReadbackContractSpec(forbidden_items=({"role": "temporary_profile"},)),
        )

        self.assertTrue(report.ok)
        self.assertIn("readback_item_absent:role=temporary_profile", {check.name for check in report.checks})

    def test_verify_document_readback_contract_rejects_invalid_forbidden_item_spec(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "model_path": "part.m3d",
                "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
                "counts": {"documents": 1, "items": 1, "tree_nodes": 1},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
                "failures": [],
                "readback": {
                    "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                    "document_tree": {"tree": {"id": "root", "name": "Part", "type": "part"}},
                    "items": {"items": [{"id": "sketch-1", "name": "ThreadSketch", "type": "sketch"}]},
                    "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                    "close_document": {"closed": True},
                },
            },
            DocumentReadbackContractSpec(forbidden_items=("temporary_profile", {"role": "temporary_profile", "numeric_tolerance": "wide"})),
        )
        failed = {check.name for check in report.checks if not check.ok}

        self.assertFalse(report.ok)
        self.assertIn("readback_item_spec:forbidden:0", failed)
        self.assertIn("readback_item_spec:forbidden:1", failed)

    def test_verify_document_readback_contract_reports_forbidden_item_presence(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": True,
                "model_path": "part.m3d",
                "document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"},
                "counts": {"documents": 1, "items": 1, "tree_nodes": 1},
                "checks": [
                    {"name": "open_document", "ok": True},
                    {"name": "document_path_matches_model_name", "ok": True},
                    {"name": "close_document", "ok": True},
                ],
                "failures": [],
                "readback": {
                    "open_document": {"document": {"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}},
                    "document_tree": {"tree": {"id": "root", "name": "Part", "type": "part"}},
                    "items": {
                        "items": [
                            {
                                "id": "tmp-1",
                                "name": "TemporaryProfile",
                                "type": "sketch",
                                "role": "temporary_profile",
                                "geometry": {"kind": "scratch_profile", "points": [[0, 0], [1, 1]]},
                            }
                        ]
                    },
                    "list_documents": {"documents": [{"id": "doc-1", "name": "part.m3d", "path": "part.m3d"}]},
                    "close_document": {"closed": True},
                },
            },
            DocumentReadbackContractSpec(forbidden_items=({"role": "temporary_profile"},)),
        )
        failed = {check.name for check in report.checks if not check.ok}
        forbidden_check = next(check for check in report.checks if check.name == "readback_item_absent:role=temporary_profile")

        self.assertFalse(report.ok)
        self.assertIn("readback_item_absent:role=temporary_profile", failed)
        self.assertEqual(
            forbidden_check.actual["matches"][0],
            {
                "id": "tmp-1",
                "name": "TemporaryProfile",
                "type": "sketch",
                "role": "temporary_profile",
                "source": "items",
                "extra_keys": ["geometry"],
            },
        )

    def test_verify_document_readback_contract_reports_failures(self) -> None:
        report = verify_document_readback_contract(
            {
                "ok": False,
                "counts": {"documents": 0, "items": 0, "tree_nodes": 0},
                "checks": [
                    {"name": "open_document", "ok": False},
                    {"name": "document_path_matches_model_name", "ok": False},
                    {"name": "close_document", "ok": False},
                ],
            },
            DocumentReadbackContractSpec(min_items=1, min_tree_nodes=1),
        )
        failed = {check.name for check in report.checks if not check.ok}

        self.assertFalse(report.ok)
        self.assertIn("readback_report_ok", failed)
        self.assertIn("minimum_documents", failed)
        self.assertIn("open_document_check", failed)
        self.assertIn("close_document_check", failed)

    def test_build_run_ledger_indexes_successful_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_model = root / "run1.m3d"
            second_model = root / "run2.m3d"
            first_model.write_bytes(b"model-1")
            second_model.write_bytes(b"model-2")
            for name, model_path in (
                ("real_task", first_model),
                ("real_task_2", second_model),
            ):
                run_dir = root / name
                run_dir.mkdir()
                (run_dir / "summary.json").write_text(
                    f'{{"ok": true, "scenario": "external_helical_thread", "designation": "M12x1", "output_path": "{model_path.as_posix()}"}}',
                    encoding="utf-8",
                )
                (run_dir / "07_diagnostic_bundle.json").write_text('{"ok": true}', encoding="utf-8")
                (run_dir / "08_operation_contract.json").write_text('{"ok": true}', encoding="utf-8")

            ledger = build_run_ledger(root, run_prefix="real_task")

        self.assertTrue(ledger["ok"])
        self.assertEqual(ledger["counts"]["runs"], 2)
        self.assertEqual(ledger["counts"]["successful_runs"], 2)
        self.assertEqual(ledger["latest_successful_run"]["name"], "real_task_2")

    def test_build_run_ledger_reports_missing_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "real_task"
            run_dir.mkdir()
            (run_dir / "summary.json").write_text(
                '{"ok": true, "scenario": "external_helical_thread", "output_path": "missing.m3d"}',
                encoding="utf-8",
            )
            (run_dir / "07_diagnostic_bundle.json").write_text('{"ok": true}', encoding="utf-8")
            (run_dir / "08_operation_contract.json").write_text('{"ok": true}', encoding="utf-8")

            ledger = build_run_ledger(root, run_prefix="real_task")

        self.assertFalse(ledger["ok"])
        self.assertEqual(ledger["counts"]["successful_runs"], 0)
        self.assertFalse(ledger["runs"][0]["model_exists"])

    def test_compare_run_regression_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name, size in (("real_task", 1000), ("real_task_2", 1050)):
                run_dir = root / name
                run_dir.mkdir()
                model_path = run_dir / "part.m3d"
                model_path.write_bytes(b"x" * size)
                (run_dir / "summary.json").write_text(
                    (
                        '{"ok": true, "scenario": "external_helical_thread", "designation": "M12x1", '
                        '"diagnostics_ok": true, "operation_contract_ok": true, "thread_geometry_probes_ok": true, '
                        '"geometry_probe_count": 24, "operation_count": 8, "variable_count": 7, '
                        f'"auxiliary_hidden_count": 6, "output_path": "{model_path.as_posix()}", "output_size_bytes": {size}}}'
                    ),
                    encoding="utf-8",
                )
                (run_dir / "05_operation_manifest.json").write_text(
                    '{"ok": true, "counts": {"steps": 21, "operations": 8, "variables": 7, "auxiliary_objects": 6, "hidden_auxiliary_objects": 6}, '
                    '"operations": [{"operation": "create_source_body"}, {"operation": "cut_evolution"}], '
                    '"auxiliary_objects": [{"role": "spiral_axis"}, {"role": "profile_sketch"}]}',
                    encoding="utf-8",
                )
                (run_dir / "07_diagnostic_bundle.json").write_text('{"ok": true}', encoding="utf-8")
                (run_dir / "08_operation_contract.json").write_text('{"ok": true}', encoding="utf-8")
            ledger = build_run_ledger(root, run_prefix="real_task")

            regression = compare_run_regression(root / "real_task_2", ledger)

        self.assertTrue(regression["ok"])
        self.assertEqual(regression["baseline_run"], "real_task")

    def test_compare_run_regression_reports_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name, size, operation_count in (("real_task", 1000, 8), ("real_task_2", 2000, 7)):
                run_dir = root / name
                run_dir.mkdir()
                model_path = run_dir / "part.m3d"
                model_path.write_bytes(b"x" * size)
                (run_dir / "summary.json").write_text(
                    (
                        '{"ok": true, "scenario": "external_helical_thread", "designation": "M12x1", '
                        '"diagnostics_ok": true, "operation_contract_ok": true, "thread_geometry_probes_ok": true, '
                        '"geometry_probe_count": 24, '
                        f'"operation_count": {operation_count}, "variable_count": 7, "auxiliary_hidden_count": 6, '
                        f'"output_path": "{model_path.as_posix()}", "output_size_bytes": {size}}}'
                    ),
                    encoding="utf-8",
                )
                (run_dir / "05_operation_manifest.json").write_text(
                    (
                        '{"ok": true, "counts": {"steps": 21, '
                        f'"operations": {operation_count}, "variables": 7, "auxiliary_objects": 6, "hidden_auxiliary_objects": 6}}, '
                        '"operations": [{"operation": "create_source_body"}, {"operation": "cut_evolution"}], '
                        '"auxiliary_objects": [{"role": "spiral_axis"}, {"role": "profile_sketch"}]}'
                    ),
                    encoding="utf-8",
                )
                (run_dir / "07_diagnostic_bundle.json").write_text('{"ok": true}', encoding="utf-8")
                (run_dir / "08_operation_contract.json").write_text('{"ok": true}', encoding="utf-8")
            ledger = build_run_ledger(root, run_prefix="real_task")

            regression = compare_run_regression(
                root / "real_task_2",
                ledger,
                OperationRegressionSpec(model_size_tolerance_ratio=0.10),
            )
        failed = {check["name"] for check in regression["failures"]}

        self.assertFalse(regression["ok"])
        self.assertIn("summary_count:operation_count", failed)
        self.assertIn("manifest_count:operations", failed)
        self.assertIn("model_size_delta_ratio", failed)

    def test_build_failure_triage_reports_ok_when_no_failures(self) -> None:
        triage = build_failure_triage(
            {
                "diagnostics": {
                    "stage": "diagnostics",
                    "ok": True,
                    "checks": [{"name": "output_exists", "ok": True}],
                }
            }
        )

        self.assertTrue(triage["ok"])
        self.assertEqual(triage["counts"]["items"], 0)
        self.assertEqual(triage["next_actions"], [])

    def test_build_failure_triage_classifies_failures(self) -> None:
        triage = build_failure_triage(
            {
                "operation_invariants": {
                    "stage": "operation_invariants",
                    "ok": False,
                    "checks": [
                        {"name": "output_exists", "ok": False, "expected": True, "actual": False},
                        {"name": "preview_operation:cut_evolution.pitch", "ok": False, "expected": 1.0, "actual": 1.25},
                    ],
                },
                "operation_contract": {
                    "stage": "operation_contract",
                    "ok": False,
                    "checks": [{"name": "auxiliary_contract_hidden", "ok": False, "expected": [], "actual": ["profile_sketch"]}],
                },
            }
        )

        self.assertFalse(triage["ok"])
        self.assertEqual(triage["counts"]["items"], 3)
        self.assertEqual(triage["counts"]["critical"], 1)
        self.assertEqual(triage["counts"]["high"], 1)
        self.assertEqual(triage["counts"]["medium"], 1)
        self.assertEqual(triage["items"][0]["check"], "output_exists")
        self.assertEqual(triage["items"][0]["category"], "model_artifact")
        self.assertEqual(triage["items"][1]["category"], "geometry")
        self.assertEqual(triage["items"][2]["category"], "auxiliary_visibility")

    def test_build_reproducibility_snapshot_hashes_reports_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            model_path = run_dir / "part.m3d"
            model_path.write_bytes(b"kompas-model")
            (run_dir / "summary.json").write_text(
                f'{{"ok": true, "output_path": "{model_path.as_posix()}"}}',
                encoding="utf-8",
            )
            (run_dir / "02_kompas_task_payload.json").write_text('{"scenario": "external_helical_thread"}', encoding="utf-8")

            snapshot = build_reproducibility_snapshot(
                run_dir,
                required_files=("02_kompas_task_payload.json", "summary.json"),
            )

        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["counts"]["files"], 3)
        self.assertEqual(snapshot["counts"]["json_files"], 2)
        self.assertEqual(snapshot["counts"]["model_files"], 1)
        self.assertEqual(len(snapshot["fingerprint"]), 64)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in snapshot["files"]))

    def test_build_reproducibility_snapshot_reports_missing_required_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            (run_dir / "summary.json").write_text('{"ok": true}', encoding="utf-8")

            snapshot = build_reproducibility_snapshot(
                run_dir,
                required_files=("missing.json", "summary.json"),
            )

        failed = {check["name"] for check in snapshot["failures"]}
        self.assertFalse(snapshot["ok"])
        self.assertIn("file_exists:missing.json", failed)

    def test_build_human_audit_report_renders_success_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            model_path = run_dir / "part.m3d"
            model_path.write_bytes(b"model")
            (run_dir / "summary.json").write_text(
                (
                    '{"ok": true, "scenario": "external_helical_thread", "designation": "M12x1", '
                    f'"output_path": "{model_path.as_posix()}", "output_size_bytes": 5, '
                    '"geometry_probe_count": 24, "operation_count": 8, "variable_count": 7, "auxiliary_hidden_count": 6}'
                ),
                encoding="utf-8",
            )
            (run_dir / "07_diagnostic_bundle.json").write_text('{"ok": true}', encoding="utf-8")
            (run_dir / "08_operation_contract.json").write_text('{"ok": true}', encoding="utf-8")
            (run_dir / "09_run_ledger.json").write_text('{"ok": true, "counts": {"runs": 2}}', encoding="utf-8")
            (run_dir / "10_regression_comparison.json").write_text('{"ok": true}', encoding="utf-8")
            (run_dir / "11_failure_triage.json").write_text('{"ok": true, "items": [], "counts": {}}', encoding="utf-8")
            (run_dir / "12_reproducibility_snapshot.json").write_text(
                '{"ok": true, "fingerprint": "abc", "counts": {"files": 13}}',
                encoding="utf-8",
            )

            audit = build_human_audit_report(run_dir)

        self.assertTrue(audit["ok"])
        self.assertIn("# KOMPAS CAD Run Audit", audit["markdown"])
        self.assertIn("Overall: OK", audit["markdown"])
        self.assertIn("Fingerprint: `abc`", audit["markdown"])

    def test_build_human_audit_report_includes_triage_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            (run_dir / "summary.json").write_text(
                '{"ok": false, "scenario": "external_helical_thread", "designation": "M12x1"}',
                encoding="utf-8",
            )
            (run_dir / "07_diagnostic_bundle.json").write_text('{"ok": false}', encoding="utf-8")
            (run_dir / "08_operation_contract.json").write_text('{"ok": true}', encoding="utf-8")
            (run_dir / "09_run_ledger.json").write_text('{"ok": true}', encoding="utf-8")
            (run_dir / "10_regression_comparison.json").write_text('{"ok": true}', encoding="utf-8")
            (run_dir / "11_failure_triage.json").write_text(
                (
                    '{"ok": false, "items": ['
                    '{"severity": "critical", "category": "model_artifact", "source": "operation_invariants", '
                    '"check": "output_exists", "action": "rerun"}], '
                    '"counts": {"critical": 1, "high": 0, "medium": 0, "low": 0}}'
                ),
                encoding="utf-8",
            )
            (run_dir / "12_reproducibility_snapshot.json").write_text('{"ok": true}', encoding="utf-8")

            audit = build_human_audit_report(run_dir)

        self.assertFalse(audit["ok"])
        self.assertEqual(audit["counts"]["triage_items"], 1)
        self.assertIn("Failure Triage", audit["markdown"])
        self.assertIn("model_artifact", audit["markdown"])


if __name__ == "__main__":
    unittest.main()
