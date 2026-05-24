from __future__ import annotations

from typing import Any, Protocol

from .document_preflight import preflight_document_context
from .operation_executor import execute_primitive_operation


class KompasDocumentStateAdapter(Protocol):
    def get_session_state(self) -> dict[str, Any]: ...

    def list_documents(self) -> dict[str, Any]: ...

    def get_document_tree(self, document_id: str | None = None) -> dict[str, Any]: ...

    def get_items(self, document_id: str | None = None, item_ids: list[str] | None = None) -> dict[str, Any]: ...


def get_active_document_state(
    adapter: KompasDocumentStateAdapter,
    *,
    document_id: str | None = None,
    require_active_document: bool = True,
    include_tree: bool = False,
    include_items: bool = False,
    max_items: int = 25,
    stage: str = "active_document_state",
) -> dict[str, Any]:
    preflight = preflight_document_context(
        adapter,
        document_id=document_id,
        require_active_document=require_active_document,
    )
    state: dict[str, Any] | None = None

    def run_operation() -> dict[str, Any]:
        nonlocal state
        document = preflight.get("document") if isinstance(preflight, dict) else None
        document_ref = _document_ref(document, document_id)
        result: dict[str, Any] = {
            "ok": document is not None,
            "document": document,
            "session": preflight.get("session") if isinstance(preflight, dict) else None,
            "documents_count": preflight.get("documents_count") if isinstance(preflight, dict) else None,
            "counts": {},
            "steps": [],
        }

        if include_tree:
            tree_payload = adapter.get_document_tree(document_id=document_ref)
            tree_payload_ok = isinstance(tree_payload, dict)
            tree = tree_payload.get("tree") if tree_payload_ok else None
            tree_ok = tree_payload_ok and isinstance(tree, dict)
            result["steps"].append(
                {
                    "step": "read_tree",
                    "ok": tree_ok,
                    "expected": "tree_payload_object",
                    "actual": type(tree_payload).__name__ if not tree_payload_ok else type(tree).__name__,
                }
            )
            if not tree_ok:
                result["ok"] = False
            result["tree_preview"] = _tree_preview(tree)
            result["counts"]["tree_nodes"] = _count_tree_nodes(tree)

        if include_items:
            items_payload = adapter.get_items(document_id=document_ref)
            items_payload_ok = isinstance(items_payload, dict)
            items = items_payload.get("items") if items_payload_ok else None
            items_ok = isinstance(items, list)
            result["steps"].append(
                {
                    "step": "read_items",
                    "ok": items_ok,
                    "expected": "items_payload_list",
                    "actual": type(items_payload).__name__ if not items_payload_ok else type(items).__name__,
                }
            )
            if not items_ok:
                result["ok"] = False
            item_rows = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
            result["items_preview"] = [_item_preview(item) for item in item_rows[: max(0, max_items)]]
            result["counts"]["items"] = len(item_rows)
            result["counts"]["items_returned"] = min(len(item_rows), max(0, max_items))

        state = result
        return result

    envelope = execute_primitive_operation(
        "get_active_document_state",
        run_operation,
        preflight=preflight,
        stage=stage,
        require_result=True,
    )
    if state is not None:
        envelope["state"] = state
    return envelope


def _document_ref(document: Any, fallback: str | None) -> str | None:
    if isinstance(document, dict):
        for key in ("id", "path", "name"):
            value = document.get(key)
            if value:
                return str(value)
    return fallback


def _tree_preview(node: Any) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    children = node.get("children")
    child_rows = [child for child in children if isinstance(child, dict)] if isinstance(children, list) else []
    preview = _item_preview(node)
    preview["children_count"] = len(child_rows)
    preview["children"] = [_item_preview(child) for child in child_rows[:10]]
    return preview


def _item_preview(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("id", "name", "type", "role", "path", "reference", "active", "visible", "hidden", "changed")
        if key in item
    }


def _count_tree_nodes(node: Any) -> int:
    if not isinstance(node, dict):
        return 0
    children = node.get("children")
    if not isinstance(children, list):
        return 1
    return 1 + sum(_count_tree_nodes(child) for child in children if isinstance(child, dict))
