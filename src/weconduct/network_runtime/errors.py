from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Mapping


_NETWORK_ERROR_CODE = re.compile(r"\b(network\.[a-z0-9_]+)\b")
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(?<![a-z0-9_-])(?P<name>[a-z0-9_-]*(?:token|password|secret|cookie|authorization|credential|api[-_]?key)[a-z0-9_-]*)(?P<separator>=|:\s*)(?P<value>[^\s&#]+)"
)
_URL_USERINFO = re.compile(r"(?i)(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<userinfo>[^/@\s]+)@")


@dataclass(frozen=True)
class NetworkExecutionError:
    """网络运行时向节点和观察层公开的脱敏错误上下文。"""

    error_code: str
    message: str
    details: Mapping[str, object]
    request_id: str | None
    node_id: str | None
    network_context_id: str | None
    retry_attempt: int

    def __post_init__(self) -> None:
        if not self.error_code.startswith("network."):
            raise ValueError("network error_code must start with 'network.'")
        if self.retry_attempt < 1:
            raise ValueError("retry_attempt must be at least 1")

    def with_retry_attempt(self, retry_attempt: int) -> "NetworkExecutionError":
        return replace(self, retry_attempt=retry_attempt)

    def to_dict(self) -> dict[str, object]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": dict(self.details),
            "request_id": self.request_id,
            "node_id": self.node_id,
            "network_context_id": self.network_context_id,
            "retry_attempt": self.retry_attempt,
        }


def build_network_error(
    error: BaseException | str,
    *,
    operation: object,
    snapshot: object,
    error_code: str | None = None,
    details: Mapping[str, object] | None = None,
    retry_attempt: int = 1,
) -> NetworkExecutionError:
    raw_message = str(error) or type(error).__name__
    normalized_code = error_code or _infer_error_code(error, raw_message)
    return NetworkExecutionError(
        error_code=normalized_code,
        message=redact_network_message(raw_message),
        details=dict(details or {}),
        request_id=_string_attribute(operation, "request_id"),
        node_id=_string_attribute(operation, "node_id"),
        network_context_id=_string_attribute(snapshot, "context_id"),
        retry_attempt=retry_attempt,
    )


def _infer_error_code(error: BaseException | str, message: str) -> str:
    explicit = _NETWORK_ERROR_CODE.search(message)
    if explicit is not None:
        return explicit.group(1)
    class_name = type(error).__name__.lower()
    if "timeout" in class_name:
        return "network.timeout"
    if "tls" in class_name or "ssl" in class_name:
        return "network.tls_failed"
    if "proxy" in class_name:
        return "network.proxy_failed"
    if "connect" in class_name:
        return "network.connection_failed"
    return "network.transport_failed"


def redact_network_message(message: str) -> str:
    """将可公开的网络错误文本中的认证材料和 URL 凭据替换为占位符。"""
    without_userinfo = _URL_USERINFO.sub(
        lambda match: f"{match.group('scheme')}<redacted>@",
        message,
    )
    return _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group('name')}=<redacted>",
        without_userinfo,
    )


def _string_attribute(value: object, attribute: str) -> str | None:
    candidate = getattr(value, attribute, None)
    return candidate if isinstance(candidate, str) and candidate else None
