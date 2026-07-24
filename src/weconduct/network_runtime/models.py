from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Mapping

if TYPE_CHECKING:
    from .resources import ResponseBodyRef


@dataclass(frozen=True)
class NetworkContextSnapshot:
    context_id: str | None
    context_epoch: int | None = None
    parent_id: str | None = None
    branch_id: str | None = None
    base_url: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    query: Mapping[str, str] = field(default_factory=dict, repr=False)
    cookies: Mapping[str, str] = field(default_factory=dict, repr=False)
    auth: object | None = field(default=None, repr=False)
    tls: object | None = None
    proxy: object | None = None
    timeout_seconds: float | None = None
    response_limits: Mapping[str, object] = field(default_factory=dict)
    retry_policy: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class NetworkOperation:
    operation_id: str
    session_id: str
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    content: bytes | str | None = None
    upload_file_path: Path | None = None
    timeout_seconds: float = 30.0
    response_storage: Literal["auto", "file"] = "auto"

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
        if self.response_storage not in {"auto", "file"}:
            raise ValueError("response_storage must be 'auto' or 'file'")
        if self.upload_file_path is not None and self.content is not None:
            raise ValueError("upload_file_path and content cannot both be set")


@dataclass(frozen=True)
class NetworkResult:
    status: str
    operation_id: str
    session_id: str
    status_code: int | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    body_ref: ResponseBodyRef | None = None
    final_url: str | None = None
    duration_ms: float | None = None
    transport_error: str | None = None
