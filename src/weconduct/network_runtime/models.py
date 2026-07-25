from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import AsyncIterable
from typing import TYPE_CHECKING, Literal, Mapping
from uuid import uuid4

from .errors import NetworkExecutionError

if TYPE_CHECKING:
    from .resources import ResponseBodyRef


@dataclass(frozen=True)
class NetworkContextSnapshot:
    context_id: str | None
    context_epoch: int | None = None
    parent_id: str | None = None
    branch_id: str | None = None
    base_url: str | None = None
    headers: Mapping[str, object] = field(default_factory=dict, repr=False)
    query: Mapping[str, str] = field(default_factory=dict, repr=False)
    cookies: Mapping[str, object] = field(default_factory=dict, repr=False)
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
    headers: Mapping[str, object] = field(default_factory=dict)
    query: Mapping[str, str] = field(default_factory=dict)
    content: bytes | str | None = None
    upload_file_path: Path | None = None
    upload_stream: AsyncIterable[bytes] | None = None
    timeout_seconds: float = 30.0
    response_storage: Literal["auto", "file"] = "auto"
    request_id: str | None = None
    node_id: str | None = None

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
        upload_sources = sum(
            source is not None
            for source in (self.content, self.upload_file_path, self.upload_stream)
        )
        if upload_sources > 1:
            raise ValueError("content, upload_file_path and upload_stream are mutually exclusive")
        if self.request_id is None:
            object.__setattr__(self, "request_id", f"{self.operation_id}-{uuid4().hex}")
        elif not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must be a non-empty string or None")


@dataclass(frozen=True)
class NetworkResult:
    status: str
    operation_id: str
    session_id: str
    status_code: int | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    body_ref: ResponseBodyRef | None = None
    final_url: str | None = None
    set_cookies: Mapping[str, str | None] = field(default_factory=dict, repr=False)
    duration_ms: float | None = None
    transport_error: str | None = None
    error: NetworkExecutionError | None = None
