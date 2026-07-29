from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import SensitiveRef


_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "authorization",
        "client_secret",
        "cookie",
        "password",
        "proxy_authorization",
        "proxy_password",
        "refresh_token",
        "secret",
        "set_cookie",
        "token",
        "x_access_token",
        "x_api_key",
        "x_auth_token",
    }
)
_SENSITIVE_RESPONSE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "proxy-authorization",
        "set-cookie",
        "x-access-token",
        "x-api-key",
        "x-auth-token",
    }
)
_SENSITIVE_COMPACT_FIELD_NAMES = frozenset(
    {
        "apikey",
        "accesskey",
        "privatekey",
        "secretkey",
        "xapikey",
    }
)
_NON_SENSITIVE_STRUCTURE_FIELD_NAMES = frozenset(
    {
        "arrived_tokens",
        "token_context",
        "token_queue",
    }
)


def redact_sensitive_payload(value: object, *, secret_values: Iterable[object] = ()) -> Any:
    secrets = tuple(item for item in secret_values if item is not None)
    return _redact(value, secrets, parent_key=None)


def _redact(value: object, secrets: tuple[object, ...], *, parent_key: str | None) -> Any:
    if isinstance(value, SensitiveRef):
        return "<sensitive-ref>"
    if any(type(value) is type(secret) and value == secret for secret in secrets):
        return "<redacted>"
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            if isinstance(secret, str) and secret:
                redacted = redacted.replace(secret, "<redacted>")
        return _redact_sensitive_url_query(redacted, parent_key=parent_key)
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_name = str(key)
            if (
                _is_sensitive_field(key_name)
                and not _is_debug_variable_descriptor_name(parent_key)
            ) or _is_sensitive_mapping_value(
                parent_key=parent_key,
                key_name=key_name,
            ):
                redacted[key_name] = "<redacted>"
                continue
            redacted[key_name] = _redact(item, secrets, parent_key=key_name)
        return redacted
    if isinstance(value, list):
        return [_redact(item, secrets, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item, secrets, parent_key=parent_key) for item in value)
    return value


def _is_debug_variable_descriptor_name(parent_key: str | None) -> bool:
    return parent_key == "variable_descriptors"


def _is_sensitive_field(field_name: str) -> bool:
    normalized = field_name.strip().lower().replace("-", "_")
    if normalized in _NON_SENSITIVE_STRUCTURE_FIELD_NAMES:
        return False
    if normalized in _SENSITIVE_FIELD_NAMES:
        return True
    compact = normalized.replace("_", "")
    if compact in _SENSITIVE_COMPACT_FIELD_NAMES:
        return True
    return any(
        marker in normalized
        for marker in ("password", "secret", "token", "credential")
    )


def _is_sensitive_mapping_value(*, parent_key: str | None, key_name: str) -> bool:
    if parent_key is None:
        return False
    normalized_parent = parent_key.strip().lower().replace("-", "_")
    normalized_key = key_name.strip().lower()
    if normalized_parent in {"cookies", "set_cookies"}:
        return True
    if normalized_parent == "headers":
        return normalized_key in _SENSITIVE_RESPONSE_HEADERS
    if normalized_parent in {"cookie", "set_cookie"}:
        return normalized_key == "value"
    return False


def _redact_sensitive_url_query(value: str, *, parent_key: str | None) -> str:
    if parent_key is None:
        return value
    normalized_key = parent_key.strip().lower().replace("-", "_")
    if normalized_key != "url" and not normalized_key.endswith("_url"):
        return value
    parsed = urlsplit(value)
    if not parsed.query:
        return value
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    redacted_items = [
        (key, "<redacted>" if _is_sensitive_field(key) else item)
        for key, item in query_items
    ]
    if query_items == redacted_items:
        return value
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(redacted_items),
            parsed.fragment,
        )
    )
