from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConfigurationDomain:
    scope: str
    key: str
    label: str
    order: int


@dataclass(frozen=True)
class ConfigField:
    scope: str
    domain: str
    key: str
    field_type: str
    default: Any
    consumer: str | None = None
    risk_level: str = "normal"
    status: str = "active"
    editable: bool = True
    order: int = 0
    widget: str | None = None
    options: tuple[str, ...] = field(default_factory=tuple)
