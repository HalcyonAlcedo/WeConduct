from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .models import SensitiveRef


def redact_sensitive_payload(value: object, *, secret_values: Iterable[object] = ()) -> Any:
    secrets = tuple(
        item for item in secret_values if isinstance(item, str) and item
    )
    return _redact(value, secrets)


def _redact(value: object, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, SensitiveRef):
        return "<sensitive-ref>"
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            redacted = redacted.replace(secret, "<redacted>")
        return redacted
    if isinstance(value, Mapping):
        return {str(key): _redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item, secrets) for item in value)
    return value
