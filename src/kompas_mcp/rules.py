from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_rules_path() -> Path:
    return Path(__file__).resolve().parents[2] / "rules" / "default.json"


def load_rules(rules_path: str | None = None) -> dict[str, Any]:
    candidate = Path(rules_path) if rules_path else default_rules_path()
    with candidate.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def clean_text(value: str, rules: dict[str, Any]) -> str:
    text = value or ""
    naming_rules = rules.get("naming", {})

    if naming_rules.get("trim_spaces", True):
        text = text.strip()

    if naming_rules.get("replace_double_spaces", True):
        while "  " in text:
            text = text.replace("  ", " ")

    for char in naming_rules.get("forbidden_chars", []):
        text = text.replace(char, "")

    case_mode = naming_rules.get("case", "keep")
    if case_mode == "upper":
        text = text.upper()
    elif case_mode == "lower":
        text = text.lower()

    return text
