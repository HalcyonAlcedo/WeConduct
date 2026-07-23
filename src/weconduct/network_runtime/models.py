from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .resources import ResponseBodyRef


@dataclass(frozen=True)
class NetworkContextSnapshot:
    context_id: str | None
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NetworkOperation:
    operation_id: str
    session_id: str
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    content: bytes | str | None = None
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.operation_id.strip():
            raise ValueError("operation_id must be a non-empty string")
        if not self.session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if not self.method.strip():
            raise ValueError("method must be a non-empty string")
        if not self.url.strip():
            raise ValueError("url must be a non-empty string")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")


@dataclass(frozen=True)
class NetworkResult:
    status: str
    operation_id: str
    session_id: str
    status_code: int | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    body_ref: ResponseBodyRef | None = None
    final_url: str | None = None
    transport_error: str | None = None
