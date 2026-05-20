from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: str = "error"
    entity_ids: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }
        if self.entity_ids:
            payload["entity_ids"] = list(self.entity_ids)
        if self.details:
            payload["details"] = dict(self.details)
        return payload
