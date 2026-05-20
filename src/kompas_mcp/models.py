from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Issue:
    code: str
    severity: str
    message: str
    item_id: str
    field: str | None = None
    current_value: Any = None
    suggested_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnalysisResult:
    summary: dict[str, Any]
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "issues": [issue.to_dict() for issue in self.issues],
        }
