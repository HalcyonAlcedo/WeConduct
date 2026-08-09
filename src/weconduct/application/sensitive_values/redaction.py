from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import SensitiveRef


_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "authorization",
        "client_key",
        "client_secret",
        "cookie",
        "password",
        "proxy_authorization",
        "proxy_password",
        "refresh_token",
        "secret",
        "set_cookie",
        "sid",
        "token",
        "x_access_token",
        "x_api_key",
        "x_auth_token",
        "x_session_id",
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
        "clientkey",
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
_NON_SENSITIVE_PROTOCOL_CAPABILITY_FIELDS = frozenset(
    {
        "http1",
        "http2",
        "sse",
        "websocket",
        "graphql",
        "graphql_subscription",
        "oauth_client_credentials",
        "oauth_refresh",
        "http_proxy",
        "socks_proxy",
    }
)
_MARKED_SENSITIVE_VALUE_CONTAINERS = frozenset(
    {
        "variable_changes",
        "variable_snapshot",
        "variables",
    }
)


def redact_sensitive_payload(value: object, *, secret_values: Iterable[object] = ()) -> Any:
    secrets = tuple(item for item in secret_values if item is not None)
    return _redact(value, secrets, parent_key=None, marked_sensitive_fields=frozenset())


def _redact(
    value: object,
    secrets: tuple[object, ...],
    *,
    parent_key: str | None,
    marked_sensitive_fields: frozenset[str],
) -> Any:
    if isinstance(value, SensitiveRef):
        return "<sensitive-ref>"
    if any(type(value) is type(secret) and value == secret for secret in secrets):
        return "<redacted>"
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            if isinstance(secret, str) and secret:
                redacted = redacted.replace(secret, "<redacted>")
        return _redact_sensitive_url(redacted, parent_key=parent_key)
    if isinstance(value, Mapping):
        child_marked_sensitive_fields = _collect_marked_sensitive_fields(value)
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_name = str(key)
            if (
                key_name in marked_sensitive_fields
                or (
                not _is_non_sensitive_capability_flag(
                    parent_key=parent_key,
                    key_name=key_name,
                    value=item,
                )
                and (
                    (
                        _is_sensitive_field(key_name)
                        and not _is_debug_variable_descriptor_name(parent_key)
                    )
                    or _is_sensitive_mapping_value(
                        parent_key=parent_key,
                        key_name=key_name,
                    )
                )
                )
            ):
                redacted[key_name] = "<redacted>"
                continue
            redacted[key_name] = _redact(
                item,
                secrets,
                parent_key=key_name,
                marked_sensitive_fields=(
                    child_marked_sensitive_fields
                    if key_name in _MARKED_SENSITIVE_VALUE_CONTAINERS
                    else frozenset()
                ),
            )
        return redacted
    if isinstance(value, list):
        return [
            _redact(
                item,
                secrets,
                parent_key=parent_key,
                marked_sensitive_fields=marked_sensitive_fields,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _redact(
                item,
                secrets,
                parent_key=parent_key,
                marked_sensitive_fields=marked_sensitive_fields,
            )
            for item in value
        )
    return value


def _collect_marked_sensitive_fields(value: Mapping[object, object]) -> frozenset[str]:
    marked: set[str] = set()
    descriptors = value.get("variable_descriptors")
    if isinstance(descriptors, Mapping):
        marked.update(
            str(name)
            for name, descriptor in descriptors.items()
            if isinstance(descriptor, Mapping) and descriptor.get("sensitive") is True
        )
    explicit_fields = value.get("sensitive_fields")
    if isinstance(explicit_fields, (list, tuple, set, frozenset)):
        marked.update(str(name) for name in explicit_fields if isinstance(name, str))
    return frozenset(marked)


def _is_debug_variable_descriptor_name(parent_key: str | None) -> bool:
    return parent_key == "variable_descriptors"


def _is_non_sensitive_capability_flag(
    *,
    parent_key: str | None,
    key_name: str,
    value: object,
) -> bool:
    normalized_parent = (parent_key or "").strip().lower().replace("-", "_")
    normalized_key = key_name.strip().lower().replace("-", "_")
    return (
        normalized_parent == "protocols"
        and type(value) is bool
        and normalized_key in _NON_SENSITIVE_PROTOCOL_CAPABILITY_FIELDS
    )


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


def _redact_sensitive_url(value: str, *, parent_key: str | None) -> str:
    if parent_key is None:
        return value
    normalized_key = parent_key.strip().lower().replace("-", "_")
    if normalized_key != "url" and not normalized_key.endswith("_url"):
        return value
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    redacted_items = [
        (key, "<redacted>" if _is_sensitive_field(key) else item)
        for key, item in query_items
    ]
    netloc = parsed.netloc
    if "@" in netloc:
        _, host = netloc.rsplit("@", 1)
        netloc = f"<redacted>@{host}"
    if query_items == redacted_items and netloc == parsed.netloc:
        return value
    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            urlencode(redacted_items),
            parsed.fragment,
        )
    )
