import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from kompas_mcp.operation_runtime import (
    DocumentReadbackContractSpec,
    OperationContractSpec,
    OperationInvariantSpec,
    ThreadGeometryProbeSpec,
)
from kompas_mcp.verified_runner import run_verified_kompas_task


class VerifiedRunnerTests(unittest.TestCase):
    def test_run_verified_kompas_task_writes_standard_report_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = run_verified_kompas_task(
                payload=_payload(),
                preflight=_preflight(),
                output_base_dir=root / "real_task",
                create_part=_fake_create_part,
                invariant_spec=_invariant_spec(),
                contract_spec=_contract_spec(),
                thread_geometry_spec=_thread_spec(),
                document_readback=_fake_document_readback,
                document_readback_contract_spec=DocumentReadbackContractSpec(min_items=3, min_tree_nodes=3),
                require_document_readback=True,
                run_index_name="runs_index.json",
                stage_prefix="test_task",
            )
            second = run_verified_kompas_task(
                payload=_payload(),
                preflight=_preflight(),
                output_base_dir=root / "real_task",
                create_part=_fake_create_part,
                invariant_spec=_invariant_spec(),
                contract_spec=_contract_spec(),
                thread_geometry_spec=_thread_spec(),
                document_readback=_fake_document_readback,
                document_readback_contract_spec=DocumentReadbackContractSpec(min_items=3, min_tree_nodes=3),
                require_document_readback=True,
                run_index_name="runs_index.json",
                stage_prefix="test_task",
            )

            output_dir = Path(second["output_dir"])
            self.assertTrue(first["ok"])
            self.assertTrue(first["regression_comparison"]["ok"])
            self.assertTrue(first["regression_comparison"]["skipped"])
            self.assertTrue(second["ok"])
            self.assertEqual(output_dir.name, "real_task_2")
            self.assertTrue((output_dir / "13_audit_report.md").exists())
            self.assertTrue((output_dir / "14_com_document_readback.json").exists())
            self.assertTrue((output_dir / "15_com_readback_contract.json").exists())
            self.assertTrue((output_dir / "16_com_readback_manifest.json").exists())
            self.assertTrue((output_dir / "12_reproducibility_snapshot.json").exists())
            transaction = json.loads((output_dir / "00_transaction.json").read_text(encoding="utf-8"))
            self.assertTrue(transaction["ok"])
            self.assertEqual(transaction["phases"][-1]["name"], "finalize")
            self.assertTrue(transaction["phases"][-1]["finished"])
            self.assertTrue((output_dir.parent / "runs_index.json").exists())
            self.assertEqual(second["summary"]["latest_successful_run"], "real_task_2")
            self.assertTrue(second["summary"]["document_readback_ok"])
            self.assertTrue(second["summary"]["document_readback_contract_ok"])
            self.assertTrue(second["summary"]["document_readback_manifest_ok"])
            self.assertEqual(second["summary"]["document_readback_item_count"], 3)
            self.assertEqual(second["summary"]["document_readback_contract_failed_checks"], 0)
            self.assertEqual(second["document_readback_manifest"]["counts"]["tree_nodes"], 3)

    def test_run_verified_kompas_task_writes_transaction_on_create_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            with self.assertRaises(RuntimeError):
                run_verified_kompas_task(
                    payload=_payload(),
                    preflight=_preflight(),
                    output_base_dir=root / "real_task",
                    create_part=_failing_create_part,
                    invariant_spec=_invariant_spec(),
                    contract_spec=_contract_spec(),
                    thread_geometry_spec=_thread_spec(),
                    stage_prefix="test_task",
                )

            output_dir = root / "real_task"
            transaction = json.loads((output_dir / "00_transaction.json").read_text(encoding="utf-8"))
            error_payload = json.loads((output_dir / "03_kompas_create_error.json").read_text(encoding="utf-8"))
            phases = {phase["name"]: phase for phase in transaction["phases"]}
            self.assertFalse(transaction["ok"])
            self.assertTrue(phases["prepare"]["ok"])
            self.assertFalse(phases["create"]["ok"])
            self.assertEqual(error_payload["error_type"], "RuntimeError")
            self.assertIn("simulated KOMPAS failure", error_payload["message"])

    def test_run_verified_kompas_task_handles_malformed_preflight_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = run_verified_kompas_task(
                payload=_payload(),
                preflight={"report": []},
                output_base_dir=Path(temp_dir) / "real_task",
                create_part=_fake_create_part,
                invariant_spec=_invariant_spec(),
                contract_spec=_contract_spec(),
                thread_geometry_spec=_thread_spec(),
                stage_prefix="test_task",
            )

            self.assertFalse(run["ok"])
            self.assertFalse(run["summary"]["preflight_ok"])
            preflight_report = json.loads(
                (Path(run["output_dir"]) / "01_sketch_runtime_preflight.json").read_text(encoding="utf-8")
            )["report"]
            self.assertEqual(preflight_report["error_type"], "MalformedPayload")

    def test_run_verified_kompas_task_handles_non_object_create_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = run_verified_kompas_task(
                payload=_payload(),
                preflight=_preflight(),
                output_base_dir=Path(temp_dir) / "real_task",
                create_part=_non_object_create_part,
                invariant_spec=_invariant_spec(),
                contract_spec=_contract_spec(),
                stage_prefix="test_task",
            )

            self.assertFalse(run["ok"])
            result = json.loads((Path(run["output_dir"]) / "03_kompas_create_result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["error_type"], "MalformedPayload")
            self.assertFalse(run["summary"]["kompas_ok"])


def _payload() -> dict[str, Any]:
    return {
        "scenario": "external_helical_thread",
        "output_name": "part.m3d",
        "params": {
            "designation": "M12x1",
            "diameter": 12.0,
            "pitch": 1.0,
            "length": 14.0,
            "direction": "right",
            "auxiliary_geometry_hidden": True,
        },
    }


def _preflight() -> dict[str, Any]:
    return {
        "geometry": {"external_thread_depth": 0.6134346610139776},
        "report": {
            "stage": "preflight",
            "ok": True,
            "checks": [{"name": "closed_profile", "ok": True}],
        },
    }


def _fake_create_part(
    scenario: str,
    params: dict[str, Any],
    *,
    output_path: str,
    visible: bool,
    close_after_save: bool,
) -> dict[str, Any]:
    Path(output_path).write_bytes(b"fake-kompas-model")
    return {
        "ok": True,
        "scenario": scenario,
        "saved": True,
        "output_path": output_path,
        "steps": [
            {"step": "create_part_document", "ok": True},
            {
                "step": "part_variables",
                "ok": True,
                "applied": [{"name": "D1", "value": params["diameter"], "update_ok": True}],
                "applied_count": 1,
                "failed_count": 0,
            },
            {
                "step": "hide_helical_thread_auxiliary_geometry",
                "ok": True,
                "hidden": True,
                "objects": [
                    {"role": "spiral_axis", "ok": True, "requested_hidden": True, "hidden_after": True},
                    {"role": "profile_sketch", "ok": True, "requested_hidden": True, "hidden_after": True},
                ],
            },
        ],
        "preview": {
            "operations": [
                {
                    "operation": "create_source_body",
                    "summary": {"total_length": 20.0},
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
        },
    }


def _failing_create_part(
    scenario: str,
    params: dict[str, Any],
    *,
    output_path: str,
    visible: bool,
    close_after_save: bool,
) -> dict[str, Any]:
    raise RuntimeError("simulated KOMPAS failure")


def _non_object_create_part(
    scenario: str,
    params: dict[str, Any],
    *,
    output_path: str,
    visible: bool,
    close_after_save: bool,
) -> list[str]:
    Path(output_path).write_bytes(b"fake-kompas-model")
    return ["not", "an", "object"]


def _fake_document_readback(model_path: str) -> dict[str, Any]:
    model_name = Path(model_path).name
    document = {"id": model_path, "name": model_name, "path": model_path, "active": True, "changed": False}
    tree = {
        "id": "root",
        "name": model_name,
        "children": [{"id": "root/0", "name": "solid"}, {"id": "root/1", "name": "thread"}],
    }
    return {
        "open_document": {"document": document, "open_attempts": [{"path": model_path, "returned_document": True}]},
        "document_tree": {"document": document, "tree": tree},
        "items": {"document": document, "items": [tree, *tree["children"]], "count": 3},
        "list_documents": {"documents": [document]},
        "close_document": {"document": document, "closed": True},
    }


def _invariant_spec() -> OperationInvariantSpec:
    return OperationInvariantSpec(
        scenario="external_helical_thread",
        required_steps=("create_part_document", "hide_helical_thread_auxiliary_geometry"),
        require_auxiliary_hidden=True,
        expected_auxiliary_roles=("spiral_axis", "profile_sketch"),
        expected_operation_values={"cut_evolution": {"diameter": 12.0, "pitch": 1.0}},
    )


def _contract_spec() -> OperationContractSpec:
    return OperationContractSpec(
        scenario="external_helical_thread",
        required_sections=("sketch_runtime_preflight", "operation_invariants", "thread_geometry_probes"),
        required_artifact_roles=("model",),
        min_counts={"steps": 3, "operations": 4, "variables": 1, "auxiliary_objects": 2, "hidden_auxiliary_objects": 2},
        expected_operation_names=("create_source_body", "cut_evolution"),
        expected_variable_names=("D1",),
        expected_auxiliary_roles=("spiral_axis", "profile_sketch"),
    )


def _thread_spec() -> ThreadGeometryProbeSpec:
    return ThreadGeometryProbeSpec(
        diameter=12.0,
        pitch=1.0,
        length=14.0,
        depth=0.6134346610139776,
        min_source_total_length=14.0,
    )


if __name__ == "__main__":
    unittest.main()
