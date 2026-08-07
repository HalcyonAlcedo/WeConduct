from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


_UNSET = object()

_PENDING_INPUT_VALUE_TYPES = frozenset(
    {
        "any",
        "array",
        "boolean",
        "bool",
        "dict",
        "float",
        "int",
         "integer",
         "list",
         "json",
        "map",
        "number",
        "object",
        "password",
        "secret",
        "string",
        "text",
    }
)


class PendingInputStatus(StrEnum):
    CREATED = "created"
    WAITING = "waiting"
    SUBMITTED = "submitted"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class PendingInputField:
    field_id: str
    label: str
    value_type: str = "string"
    sensitive: bool = False
    required: bool = True
    default_value: object = field(default=_UNSET, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.field_id, str) or not self.field_id.strip():
            raise ValueError("field_id must be a non-empty string")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("label must be a non-empty string")
        if not isinstance(self.value_type, str) or not self.value_type.strip():
            raise ValueError("value_type must be a non-empty string")
        normalized_value_type = self.value_type.strip().lower()
        if normalized_value_type not in _PENDING_INPUT_VALUE_TYPES:
            raise ValueError(f"unsupported pending input value_type: {self.value_type}")
        object.__setattr__(self, "value_type", normalized_value_type)
        if self.sensitive and self.default_value is not _UNSET:
            raise ValueError("sensitive fields cannot define defaults")

    @property
    def has_default(self) -> bool:
        return self.default_value is not _UNSET


@dataclass(frozen=True)
class PendingInputRequest:
    request_id: str
    execution_id: str
    node_id: str
    fields: tuple[PendingInputField, ...]
    timeout_seconds: float = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("request_id", self.request_id),
            ("execution_id", self.execution_id),
            ("node_id", self.node_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not self.fields:
            raise ValueError("pending input requests require at least one field")
        field_ids = [field.field_id for field in self.fields]
        if len(set(field_ids)) != len(field_ids):
            raise ValueError("pending input field_id values must be unique")
        if isinstance(self.timeout_seconds, bool):
            raise ValueError("timeout_seconds must be numeric")
        try:
            timeout_seconds = float(self.timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout_seconds must be numeric") from exc
        object.__setattr__(self, "timeout_seconds", timeout_seconds)


@dataclass(frozen=True)
class PendingInputSnapshot:
    request_id: str
    execution_id: str
    node_id: str
    status: PendingInputStatus
    fields: tuple[PendingInputField, ...]
    timeout_seconds: float


@dataclass(frozen=True)
class PendingInputResult:
    request_id: str
    status: PendingInputStatus
    values: Mapping[str, object]
