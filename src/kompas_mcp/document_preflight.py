from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .runtime_errors import classify_runtime_error


class KompasDocumentPreflightAdapter(Protocol):
    def get_session_state(self) -> dict[str, Any]: ...

    def list_documents(self) -> dict[str, Any]: ...

    def get_document_tree(self, document_id: str | None = None) -> dict[str, Any]: ...

    def get_items(self, document_id: str | None = None, item_ids: list[str] | None = None) -> dict[str, Any]: ...


def preflight_document_context(
    adapter: KompasDocumentPreflightAdapter,
    *,
    document_id: str | None = None,
    require_active_document: bool = True,
    expected_document_type: str | int | None = None,
    expected_extensions: list[str] | tuple[str, ...] | None = None,
    require_tree: bool = False,
    min_tree_nodes: int = 1,
    require_items: bool = False,
    min_items: int = 1,
    stage: str = "document_preflight",
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    session = _capture_call(checks, "session_state", adapter.get_session_state)
    documents_payload = _capture_call(checks, "list_documents", adapter.list_documents)
    documents = _documents_from_payload(documents_payload)
    selected = _select_document(session, documents, document_id)
    active_document = _dict_or_none(session.get("active_document")) if isinstance(session, dict) else None

    _add_check(
        checks,
        "kompas_connected",
        bool(session.get("kompas_connected")) if isinstance(session, dict) else False,
        True,
        session.get("kompas_connected") if isinstance(session, dict) else None,
    )
    _add_check(
        checks,
        "document_selected",
        selected is not None,
        {"document_id": document_id or "<active>"},
        _document_preview(selected),
    )

    if require_active_document:
        active_ok = selected is not None and _same_document(selected, active_document)
        _add_check(
            checks,
            "active_document_selected",
            active_ok,
            True,
            {"selected": _document_preview(selected), "active": _document_preview(active_document)},
        )

    if selected is not None and expected_document_type is not None:
        actual_type = selected.get("type")
        _add_check(checks, "document_type", _same_scalar(actual_type, expected_document_type), expected_document_type, actual_type)

    if selected is not None and expected_extensions:
        expected = tuple(_normalize_extension(ext) for ext in expected_extensions)
        actual = _document_extension(selected)
        _add_check(checks, "document_extension", actual in expected, list(expected), actual)

    readback: dict[str, Any] = {}
    selected_id = str((selected or {}).get("id") or document_id or "") or None
    if require_tree and selected is not None:
        tree_payload = _capture_call(checks, "document_tree_readback", lambda: adapter.get_document_tree(document_id=selected_id))
        tree_count = _count_tree_nodes(tree_payload.get("tree") if isinstance(tree_payload, dict) else None)
        readback["tree_nodes"] = tree_count
        _add_check(checks, "min_tree_nodes", tree_count >= min_tree_nodes, {">=": min_tree_nodes}, tree_count)

    if require_items and selected is not None:
        items_payload = _capture_call(checks, "document_items_readback", lambda: adapter.get_items(document_id=selected_id))
        items = items_payload.get("items") if isinstance(items_payload, dict) else []
        items_count = len(items) if isinstance(items, list) else 0
        readback["items"] = items_count
        _add_check(checks, "min_items", items_count >= min_items, {">=": min_items}, items_count)

    return {
        "stage": stage,
        "ok": all(bool(check.get("ok")) for check in checks),
        "checks": checks,
        "session": {
            "kompas_connected": session.get("kompas_connected") if isinstance(session, dict) else None,
            "documents_count": session.get("documents_count") if isinstance(session, dict) else len(documents),
            "active_document": _document_preview(active_document),
        },
        "document": _document_preview(selected),
        "documents_count": len(documents),
        "readback": readback,
    }


def _capture_call(checks: list[dict[str, Any]], name: str, callback: Any) -> dict[str, Any]:
    try:
        payload = callback()
    except Exception as exc:
        _add_check(
            checks,
            name,
            False,
            "call succeeds",
            {
                "error": str(exc),
                "type": type(exc).__name__,
                "classification": classify_runtime_error(exc, stage=name),
            },
        )
        return {}
    if not isinstance(payload, dict):
        _add_check(
            checks,
            name,
            False,
            "object payload",
            {
                "type": type(payload).__name__,
                "classification": classify_runtime_error(f"{name} returned non-object payload", stage=name),
            },
        )
        return {}
    _add_check(checks, name, True, "call succeeds", _payload_preview(payload))
    return payload


def _add_check(checks: list[dict[str, Any]], name: str, ok: bool, expected: Any, actual: Any) -> None:
    checks.append({"name": name, "ok": bool(ok), "expected": expected, "actual": actual})


def _documents_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    documents = payload.get("documents") if isinstance(payload, dict) else []
    return [doc for doc in documents if isinstance(doc, dict)] if isinstance(documents, list) else []


def _select_document(session: dict[str, Any], documents: list[dict[str, Any]], document_id: str | None) -> dict[str, Any] | None:
    active = _dict_or_none(session.get("active_document")) if isinstance(session, dict) else None
    if document_id is None:
        return active or (documents[0] if len(documents) == 1 else None)
    candidates = [doc for doc in documents + ([active] if active else []) if doc is not None]
    for document in candidates:
        if any(_same_scalar(document.get(key), document_id) for key in ("id", "path", "name")):
            return document
    return None


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _same_document(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if left is None or right is None:
        return False
    for key in ("id", "path", "name"):
        if left.get(key) and right.get(key) and _same_scalar(left.get(key), right.get(key)):
            return True
    return left is right


def _same_scalar(left: Any, right: Any) -> bool:
    return str(left).casefold() == str(right).casefold()


def _document_preview(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None
    return {key: document.get(key) for key in ("id", "name", "path", "type", "active", "changed") if key in document}


def _payload_preview(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"type": type(payload).__name__}
    preview: dict[str, Any] = {"keys": sorted(str(key) for key in payload.keys())[:12]}
    if isinstance(payload.get("documents"), list):
        preview["documents"] = len(payload["documents"])
    if isinstance(payload.get("items"), list):
        preview["items"] = len(payload["items"])
    if "document" in payload:
        preview["document"] = _document_preview(_dict_or_none(payload.get("document")))
    return preview


def _normalize_extension(extension: str) -> str:
    value = str(extension).casefold().strip()
    return value if value.startswith(".") else f".{value}"


def _document_extension(document: dict[str, Any]) -> str:
    value = str(document.get("path") or document.get("name") or "")
    return Path(value).suffix.casefold()


def _count_tree_nodes(node: Any) -> int:
    if not isinstance(node, dict):
        return 0
    children = node.get("children")
    if not isinstance(children, list):
        return 1
    return 1 + sum(_count_tree_nodes(child) for child in children if isinstance(child, dict))
