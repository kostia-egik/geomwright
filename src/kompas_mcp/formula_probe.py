from __future__ import annotations

import json
import math
import re
import struct
import zlib
from pathlib import Path
from typing import Any, Protocol
from zipfile import ZipFile


_ASCII_RUN_RE = re.compile(r"[ -~]{5,}")
_PUBLIC_VARIABLE_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_FORMULA_REFERENCE_RE = re.compile(r"\b(?:[A-Z][A-Z0-9_]{2,}|v\d+)\b")
_INTERNAL_VARIABLE_RE = re.compile(r"\bv\d+\b")
_HUMAN_LABEL_RE = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9 ./,\-]{1,63}")
_INTERNAL_LABEL_ROLE_MAP = {
    "шаг": "pitch",
    "число витков": "turn_count",
    "расстояние": "distance",
    "вращение": "rotation",
    "нутация": "nutation",
    "прецессия": "precession",
    "координата x": "coordinate_x",
    "координата y": "coordinate_y",
    "координата z": "coordinate_z",
}


class KompasFormulaProbeAdapter(Protocol):
    def open_document(self, path: str, *, visible: bool, read_only: bool) -> dict[str, Any]: ...

    def close_document(self, *, document_id: str, save: bool) -> dict[str, Any]: ...

    def get_document_tree(self, document_id: str | None = None) -> dict[str, Any]: ...

    def list_sketches(self, document_id: str | None = None, max_items: int | None = None) -> dict[str, Any]: ...

    def list_sketch_dimensions(
        self,
        document_id: str | None = None,
        sketch_ref: str | int | None = None,
        kinds: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def list_sketch_constraints(
        self,
        document_id: str | None = None,
        sketch_ref: str | int | None = None,
        kinds: list[str] | None = None,
        max_items: int | None = None,
    ) -> dict[str, Any]: ...

    def list_features(
        self,
        document_id: str | None = None,
        kinds: list[str] | None = None,
        max_items: int | None = None,
    ) -> dict[str, Any]: ...

    def inspect_feature(
        self,
        document_id: str | None = None,
        feature: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


def probe_model_formulas(
    adapter: KompasFormulaProbeAdapter,
    *,
    model_path: str | None = None,
    document_id: str | None = None,
    output_path: str | Path | None = None,
    visible: bool = False,
    read_only: bool = True,
    close_after_probe: bool = True,
    include_contents_fallback: bool = True,
    max_sketches: int = 25,
    max_features: int = 50,
    max_constraints_per_sketch: int = 200,
) -> dict[str, Any]:
    if model_path and document_id:
        raise ValueError("model_path and document_id are mutually exclusive")

    opened_document_id = ""
    payload: dict[str, Any] = {}
    if model_path:
        open_payload = _capture_adapter_payload(
            "open_document",
            lambda: adapter.open_document(model_path, visible=visible, read_only=read_only),
        )
        payload["open_document"] = open_payload
        opened_document_id = _payload_document_id(open_payload)
        if not bool(open_payload.get("ok")) or not opened_document_id:
            contents_report = (
                inspect_m3d_formula_contents(model_path)
                if include_contents_fallback
                else {"available": False, "path": model_path, "formula_strings": [], "public_variables": []}
            )
            failure = {
                "name": "open_document",
                "ok": False,
                "details": open_payload,
            }
            result = {
                "stage": "formula_probe",
                "ok": False,
                "probe": {
                    "mode": "open_file",
                    "model_path": model_path,
                    "document_id": document_id,
                    "close_after_probe": close_after_probe,
                    "include_contents_fallback": include_contents_fallback,
                },
                "document": {},
                "summary": {
                    "sketch_count": 0,
                    "feature_count": 0,
                    "dimension_formula_count": 0,
                    "constraint_formula_count": 0,
                    "feature_variable_formula_count": 0,
                    "contents_formula_count": len(contents_report.get("formula_strings") or []),
                    "public_variable_count": len(contents_report.get("public_variables") or []),
                    "internal_variable_count": len(contents_report.get("internal_variables") or []),
                    "failures": 1,
                },
                "sketches": [],
                "features": [],
                "contents": contents_report,
                "failures": [failure],
            }
            if output_path:
                artifact = _write_probe_artifact(output_path, result)
                result["artifact"] = artifact
                if not artifact["written"]:
                    result["failures"].append(
                        {"name": "artifact_write", "ok": False, "details": artifact}
                    )
                    result["summary"]["failures"] = len(result["failures"])
            return result
        selected_document_id = opened_document_id
    else:
        selected_document_id = document_id

    tree_payload = _capture_adapter_payload(
        "document_tree",
        lambda: adapter.get_document_tree(document_id=selected_document_id),
    )
    payload["document_tree"] = tree_payload
    document = tree_payload.get("document") if isinstance(tree_payload.get("document"), dict) else {}
    if not payload.get("open_document"):
        payload["open_document"] = {
            "document": document,
            "visible": None,
            "read_only": None,
            "probe_source": "active_document",
        }

    active_document_id = str(document.get("id") or selected_document_id or "")
    sketches_payload = _capture_adapter_payload(
        "list_sketches",
        lambda: adapter.list_sketches(document_id=active_document_id or selected_document_id, max_items=max_sketches),
    )
    payload["list_sketches"] = sketches_payload

    features_payload = _capture_adapter_payload(
        "list_features",
        lambda: adapter.list_features(document_id=active_document_id or selected_document_id, max_items=max_features),
    )
    payload["list_features"] = features_payload

    sketches, sketch_failures = _probe_sketch_formulas(
        adapter,
        document_id=active_document_id or selected_document_id,
        list_payload=payload.get("list_sketches"),
        max_constraints_per_sketch=max_constraints_per_sketch,
    )
    features, feature_failures = _probe_feature_formulas(
        adapter,
        document_id=active_document_id or selected_document_id,
        list_payload=payload.get("list_features"),
    )

    contents_report = (
        inspect_m3d_formula_contents(model_path)
        if include_contents_fallback and model_path not in (None, "")
        else {"available": False, "path": model_path, "formula_strings": [], "public_variables": []}
    )

    failures = list(_payload_failures(payload))
    failures.extend(sketch_failures)
    failures.extend(feature_failures)
    if include_contents_fallback and model_path and not contents_report.get("ok", True):
        failures.append(
            {
                "name": "contents_probe",
                "ok": False,
                "details": {
                    "path": model_path,
                    "error": contents_report.get("error"),
                    "error_type": contents_report.get("error_type"),
                },
            }
        )
    if close_after_probe and opened_document_id:
        payload["close_document"] = _capture_adapter_payload(
            "close_document",
            lambda: adapter.close_document(document_id=opened_document_id, save=False),
        )
        if not payload["close_document"].get("ok"):
            failures.append({"name": "close_document", "ok": False, "details": payload["close_document"]})

    result = {
        "stage": "formula_probe",
        "ok": not failures,
        "probe": {
            "mode": "open_file" if model_path else "active_document",
            "model_path": model_path,
            "document_id": document_id,
            "close_after_probe": close_after_probe,
            "include_contents_fallback": include_contents_fallback,
        },
        "document": document,
        "summary": {
            "sketch_count": len(sketches),
            "feature_count": len(features),
            "dimension_formula_count": sum(len(item.get("dimensions") or []) for item in sketches),
            "constraint_formula_count": sum(len(item.get("constraints") or []) for item in sketches),
            "feature_variable_formula_count": sum(len(item.get("variables") or []) for item in features),
            "contents_formula_count": len(contents_report.get("formula_strings") or []),
            "public_variable_count": len(contents_report.get("public_variables") or []),
            "internal_variable_count": len(contents_report.get("internal_variables") or []),
            "failures": len(failures),
        },
        "sketches": sketches,
        "features": features,
        "contents": contents_report,
        "failures": failures,
    }
    if output_path:
        artifact = _write_probe_artifact(output_path, result)
        result["artifact"] = artifact
        if not artifact["written"]:
            result["ok"] = False
            result["failures"].append(
                {
                    "name": "artifact_write",
                    "ok": False,
                    "details": artifact,
                }
            )
            result["summary"]["failures"] = len(result["failures"])
    return result


def inspect_m3d_formula_contents(model_path: str | Path) -> dict[str, Any]:
    model = Path(model_path)
    result: dict[str, Any] = {
        "ok": False,
        "available": False,
        "path": str(model),
        "formula_strings": [],
        "public_variables": [],
        "internal_variables": [],
    }
    if not model.is_file():
        result["error"] = "model_path_not_found"
        return result

    try:
        with ZipFile(model, "r") as archive:
            raw_contents = archive.read("Contents")
    except Exception as exc:
        result.update(
            {
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        )
        return result

    try:
        decompressed = _decompress_kompas_contents(raw_contents)
        text = decompressed.decode("utf-16le", errors="ignore")
        runs = _extract_ascii_runs(text)
        public_variables = _extract_public_variables(runs)
        internal_variables = _extract_internal_variables(text)
        internal_reference_names = _extract_internal_reference_names(runs)
        internal_variables = _merge_internal_variable_placeholders(text, internal_variables, internal_reference_names)
        value_map = _extract_variable_values(
            decompressed,
            public_variables=public_variables,
            internal_variables=internal_variables,
        )
        public_variables = _merge_variable_values(public_variables, value_map)
        internal_variables = _merge_variable_values(internal_variables, value_map)
        formulas = _extract_formula_strings(
            runs,
            public_variables=public_variables,
            internal_variables=internal_variables,
        )
    except Exception as exc:
        result.update(
            {
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        )
        return result

    result.update(
        {
            "ok": True,
            "available": True,
            "compressed_size": len(raw_contents),
            "decompressed_size": len(decompressed),
            "ascii_run_count": len(runs),
            "formula_strings": formulas,
            "public_variables": public_variables,
            "internal_variables": internal_variables,
        }
    )
    return result


def _probe_sketch_formulas(
    adapter: KompasFormulaProbeAdapter,
    *,
    document_id: str | None,
    list_payload: dict[str, Any] | None,
    max_constraints_per_sketch: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sketches_payload = list_payload if isinstance(list_payload, dict) else {}
    items = sketches_payload.get("items") if isinstance(sketches_payload.get("items"), list) else []
    failures: list[dict[str, Any]] = []
    sketches: list[dict[str, Any]] = []
    for sketch in items:
        if not isinstance(sketch, dict):
            continue
        sketch_ref = sketch.get("reference")
        if sketch_ref in (None, ""):
            continue

        dimensions_payload = _capture_adapter_payload(
            f"list_sketch_dimensions:{sketch_ref}",
            lambda sketch_ref=sketch_ref: adapter.list_sketch_dimensions(document_id=document_id, sketch_ref=sketch_ref),
        )
        constraints_payload = _capture_adapter_payload(
            f"list_sketch_constraints:{sketch_ref}",
            lambda sketch_ref=sketch_ref: adapter.list_sketch_constraints(
                document_id=document_id,
                sketch_ref=sketch_ref,
                max_items=max_constraints_per_sketch,
            ),
        )

        if not dimensions_payload.get("ok"):
            failures.append({"name": "list_sketch_dimensions", "ok": False, "details": dimensions_payload})
        if not constraints_payload.get("ok"):
            failures.append({"name": "list_sketch_constraints", "ok": False, "details": constraints_payload})

        dimensions = [
            _compact_formula_item(item)
            for item in (dimensions_payload.get("items") or [])
            if isinstance(item, dict) and _item_has_formula_signal(item)
        ]
        constraints = [
            _compact_formula_item(item)
            for item in (constraints_payload.get("items") or [])
            if isinstance(item, dict) and _item_has_formula_signal(item)
        ]
        if dimensions or constraints:
            sketches.append(
                {
                    "reference": sketch_ref,
                    "name": sketch.get("name") or "",
                    "index": sketch.get("index"),
                    "dimensions": dimensions,
                    "constraints": constraints,
                }
            )
    return sketches, failures


def _probe_feature_formulas(
    adapter: KompasFormulaProbeAdapter,
    *,
    document_id: str | None,
    list_payload: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    features_payload = list_payload if isinstance(list_payload, dict) else {}
    items = features_payload.get("items") if isinstance(features_payload.get("items"), list) else []
    failures: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    for feature in items:
        if not isinstance(feature, dict):
            continue
        kind = feature.get("kind")
        index = feature.get("index")
        if kind in (None, "") or index in (None, ""):
            continue
        detail_payload = _capture_adapter_payload(
            f"inspect_feature:{kind}:{index}",
            lambda kind=kind, index=index: adapter.inspect_feature(
                document_id=document_id,
                feature={"kind": kind, "index": index},
            ),
        )
        if not detail_payload.get("ok"):
            failures.append({"name": "inspect_feature", "ok": False, "details": detail_payload})
            continue
        detail_item = detail_payload.get("item") if isinstance(detail_payload.get("item"), dict) else {}
        variables = [
            _compact_feature_variable(item)
            for item in (detail_item.get("variables") or [])
            if isinstance(item, dict) and _item_has_formula_signal(item)
        ]
        if variables:
            features.append(
                {
                    "reference": detail_item.get("reference"),
                    "name": detail_item.get("name") or feature.get("name") or "",
                    "kind": detail_item.get("kind") or kind,
                    "index": detail_item.get("index", index),
                    "variables": variables,
                }
            )
    return features, failures


def _decompress_kompas_contents(raw_contents: bytes) -> bytes:
    payload = raw_contents[2:] if raw_contents.startswith(b"KF") else raw_contents
    decompressed = bytearray()
    offset = 0
    while offset < len(payload):
        try:
            stream = zlib.decompressobj()
            chunk = stream.decompress(payload[offset:])
            consumed = len(payload[offset:]) - len(stream.unused_data)
            if consumed <= 0:
                offset += 1
                continue
            if decompressed:
                decompressed.extend(b"\n\x00")
            decompressed.extend(chunk)
            offset += consumed
        except zlib.error:
            offset += 1
    if not decompressed:
        raise ValueError("contents_stream_not_decompressed")
    return bytes(decompressed)


def _extract_ascii_runs(text: str) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for match in _ASCII_RUN_RE.finditer(text):
        candidate = " ".join(match.group(0).split())
        if len(candidate) < 5:
            continue
        runs.append({"index": match.start(), "text": candidate})
    return runs


def _extract_formula_strings(
    runs: list[dict[str, Any]],
    *,
    public_variables: list[dict[str, Any]] | None = None,
    internal_variables: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    public_catalog = {str(item.get("name") or ""): item for item in (public_variables or [])}
    internal_catalog = {str(item.get("name") or ""): item for item in (internal_variables or [])}
    formulas: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run in runs:
        text = str(run.get("text") or "").strip()
        if text in seen or not _looks_like_formula(text):
            continue
        seen.add(text)
        references = _ordered_unique(_FORMULA_REFERENCE_RE.findall(text))
        reference_details = [
            _build_reference_detail(reference, public_catalog=public_catalog, internal_catalog=internal_catalog)
            for reference in references
        ]
        formula_item = {
            "index": run.get("index"),
            "expression": text,
            "references": references,
            "scope": "internal" if re.search(r"\bv\d+\b", text) else "named",
            "reference_details": reference_details,
        }
        interpreted = _render_interpreted_expression(text, reference_details)
        if interpreted != text:
            formula_item["interpreted_expression"] = interpreted
        evaluated_value = _evaluate_formula_expression(text, reference_details)
        if evaluated_value is not None:
            formula_item["evaluated_value"] = evaluated_value
        nearby_runs = _collect_nearby_run_texts(runs, center=int(run.get("index") or 0), expression=text)
        if nearby_runs:
            formula_item["nearby_runs"] = nearby_runs
        formulas.append(formula_item)
    return formulas


def _extract_public_variables(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variables: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run in runs:
        text = str(run.get("text") or "").strip()
        if not text or _looks_like_formula(text):
            continue
        matches = list(_PUBLIC_VARIABLE_RE.finditer(text))
        if not matches:
            continue
        if "|" in text:
            name = matches[-1].group(0)
            description = text.rsplit("|", 1)[-1].strip()
            if description.endswith(name):
                description = description[: -len(name)].strip(" |-")
            context = " | ".join(part.strip() for part in text.split("|")[:-1] if part.strip())
        elif len(matches) == 1 and matches[0].span() == (0, len(text)):
            name = matches[0].group(0)
            description = ""
            context = ""
        else:
            continue
        if name in seen:
            continue
        seen.add(name)
        variables.append(
            {
                "index": run.get("index"),
                "name": name,
                "description": description or "",
                "context": context or "",
            }
        )
    return variables


def _extract_internal_variables(text: str) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for match in _INTERNAL_VARIABLE_RE.finditer(text):
        name = match.group(0)
        label = _find_internal_variable_label(text, match.end())
        if not label:
            continue
        item = {
            "index": match.start(),
            "name": name,
            "label": label,
        }
        role = _normalize_internal_label_role(label)
        if role:
            item["role"] = role
        existing = selected.get(name)
        if existing is None or _prefer_internal_variable_item(item, existing):
            selected[name] = item
    return sorted(selected.values(), key=lambda item: (int(item.get("index") or 0), str(item.get("name") or "")))


def _extract_internal_reference_names(runs: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for run in runs:
        text = str(run.get("text") or "").strip()
        if not _looks_like_formula(text):
            continue
        names.extend(reference for reference in _FORMULA_REFERENCE_RE.findall(text) if reference.startswith("v"))
    return _ordered_unique(names)


def _merge_internal_variable_placeholders(
    text: str,
    internal_variables: list[dict[str, Any]],
    internal_reference_names: list[str],
) -> list[dict[str, Any]]:
    by_name = {str(item.get("name") or ""): dict(item) for item in internal_variables if item.get("name")}
    for name in internal_reference_names:
        if name in by_name:
            continue
        first_index = text.find(name)
        by_name[name] = {
            "index": first_index if first_index >= 0 else None,
            "name": name,
        }
    return sorted(by_name.values(), key=lambda item: (int(item.get("index") or 0), str(item.get("name") or "")))


def _extract_variable_values(
    decompressed: bytes,
    *,
    public_variables: list[dict[str, Any]],
    internal_variables: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    value_map: dict[str, dict[str, Any]] = {}
    names = _ordered_unique(
        [str(item.get("name") or "") for item in public_variables + internal_variables if item.get("name")]
    )
    for name in names:
        token = name.encode("utf-16le")
        search_from = 0
        while True:
            index = decompressed.find(token, search_from)
            if index < 0:
                break
            value_offset = index + len(token) + 7
            if value_offset + 8 <= len(decompressed):
                try:
                    value = struct.unpack("<d", decompressed[value_offset : value_offset + 8])[0]
                except struct.error:
                    value = math.nan
                if math.isfinite(value) and abs(value) < 1e12:
                    value_map[name] = {
                        "byte_index": index,
                        "value": float(value),
                    }
                    break
            search_from = index + 2
    return value_map


def _merge_variable_values(
    variables: list[dict[str, Any]],
    value_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for item in variables:
        payload = dict(item)
        value_item = value_map.get(str(item.get("name") or ""))
        if isinstance(value_item, dict):
            if "value" in value_item:
                payload["value"] = value_item["value"]
            if "byte_index" in value_item:
                payload["byte_index"] = value_item["byte_index"]
        merged.append(payload)
    return merged


def _find_internal_variable_label(text: str, start: int, *, window: int = 160) -> str:
    raw_window = text[start : start + window]
    cleaned = re.sub(r"^[\x00-\x1f\ufffe\uffff]+", "", raw_window)
    match = _HUMAN_LABEL_RE.search(cleaned)
    if match is None:
        return ""
    candidate = match.group(0).strip(" .,/()-")
    if len(candidate) < 2 or _looks_like_formula(candidate):
        return ""
    if _FORMULA_REFERENCE_RE.search(candidate):
        return ""
    if _INTERNAL_VARIABLE_RE.fullmatch(candidate) or _PUBLIC_VARIABLE_RE.fullmatch(candidate):
        return ""
    return candidate


def _normalize_internal_label_role(label: str) -> str:
    key = " ".join(str(label).strip().lower().split())
    return _INTERNAL_LABEL_ROLE_MAP.get(key, "")


def _prefer_internal_variable_item(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    candidate_score = _internal_variable_item_score(candidate)
    existing_score = _internal_variable_item_score(existing)
    if candidate_score != existing_score:
        return candidate_score > existing_score
    return int(candidate.get("index") or 0) > int(existing.get("index") or 0)


def _internal_variable_item_score(item: dict[str, Any]) -> tuple[int, int]:
    label = str(item.get("label") or "")
    has_role = 1 if item.get("role") else 0
    has_cyrillic = 1 if re.search(r"[А-Яа-яЁё]", label) else 0
    return has_role, has_cyrillic


def _build_reference_detail(
    reference: str,
    *,
    public_catalog: dict[str, dict[str, Any]],
    internal_catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if reference in public_catalog:
        item = public_catalog[reference]
        detail: dict[str, Any] = {"name": reference, "scope": "named"}
        if item.get("description"):
            detail["description"] = item.get("description")
        if item.get("context"):
            detail["context"] = item.get("context")
        if item.get("value") is not None:
            detail["value"] = item.get("value")
        return detail
    if reference in internal_catalog:
        item = internal_catalog[reference]
        detail = {"name": reference, "scope": "internal"}
        if item.get("label"):
            detail["label"] = item.get("label")
        if item.get("role"):
            detail["role"] = item.get("role")
        if item.get("value") is not None:
            detail["value"] = item.get("value")
        return detail
    return {"name": reference, "scope": "internal" if reference.startswith("v") else "named"}


def _render_interpreted_expression(expression: str, reference_details: list[dict[str, Any]]) -> str:
    if not reference_details:
        return expression
    replacements: dict[str, str] = {}
    for detail in reference_details:
        name = str(detail.get("name") or "")
        replacement = str(detail.get("role") or detail.get("label") or detail.get("description") or "").strip()
        if not name or not replacement:
            continue
        replacements[name] = replacement.replace(" ", "_")
    if not replacements:
        return expression
    return re.sub(
        r"\b(?:[A-Z][A-Z0-9_]{2,}|v\d+)\b",
        lambda match: replacements.get(match.group(0), match.group(0)),
        expression,
    )


def _evaluate_formula_expression(expression: str, reference_details: list[dict[str, Any]]) -> float | None:
    namespace: dict[str, float] = {}
    for detail in reference_details:
        name = str(detail.get("name") or "")
        value = detail.get("value")
        if not name or value is None:
            continue
        try:
            namespace[name] = float(value)
        except (TypeError, ValueError):
            continue
    references = _ordered_unique(_FORMULA_REFERENCE_RE.findall(expression))
    if not references or any(reference not in namespace for reference in references):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_()+\-/* .]+", expression):
        return None
    try:
        value = eval(expression, {"__builtins__": {}}, namespace)
    except Exception:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _collect_nearby_run_texts(
    runs: list[dict[str, Any]],
    *,
    center: int,
    expression: str,
    window: int = 240,
    limit: int = 6,
) -> list[str]:
    nearby: list[str] = []
    for run in runs:
        text = str(run.get("text") or "").strip()
        if not text or text == expression:
            continue
        if abs(int(run.get("index") or 0) - center) > window:
            continue
        nearby.append(text)
        if len(nearby) >= limit:
            break
    return nearby


def _looks_like_formula(text: str) -> bool:
    if not text or not any(operator in text for operator in ("+", "-", "*", "/")):
        return False
    if not _FORMULA_REFERENCE_RE.search(text):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_()+\-/* .]+", text))


def _item_has_formula_signal(item: dict[str, Any]) -> bool:
    return any(item.get(key) not in (None, "") for key in ("expression", "variable", "value"))


def _compact_formula_item(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "index": item.get("index"),
        "kind": item.get("kind"),
        "reference": item.get("reference"),
    }
    for key in ("expression", "variable", "value", "name", "fingerprint"):
        if item.get(key) not in (None, ""):
            payload[key] = item.get(key)
    return payload


def _compact_feature_variable(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"index": item.get("index")}
    for key in ("name", "expression", "value", "parameterNote", "note"):
        if item.get(key) not in (None, ""):
            payload[key] = item.get(key)
    return payload


def _ordered_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _capture_adapter_payload(name: str, callback: Any) -> dict[str, Any]:
    try:
        payload = callback()
    except Exception as exc:
        return {
            "ok": False,
            "name": name,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
    normalized = dict(payload) if isinstance(payload, dict) else {"payload": payload}
    normalized.setdefault("ok", True)
    normalized["name"] = name
    return normalized


def _payload_document_id(payload: dict[str, Any]) -> str:
    document = payload.get("document")
    return str(document.get("id") or "") if isinstance(document, dict) else ""


def _payload_failures(payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for name, item in payload.items():
        if not isinstance(item, dict):
            continue
        if item.get("ok", True):
            continue
        failures.append({"name": name, "ok": False, "details": item})
    return failures


def _write_probe_artifact(output_path: str | Path, result: dict[str, Any]) -> dict[str, Any]:
    target = Path(output_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        return {
            "written": False,
            "path": str(target),
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
    return {
        "written": True,
        "path": str(target),
        "size": target.stat().st_size,
    }
