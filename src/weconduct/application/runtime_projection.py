from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from weconduct.application.sensitive_values.redaction import redact_sensitive_payload
from weconduct.network_runtime.resources import ResponseBodyRef


_CONFIG_FIELDS_WITH_SENSITIVE_VALUES = frozenset(
    {
        "auth",
        "body",
        "cookies",
        "headers",
        "initial_variables",
        "proxy",
        "query",
    }
)


def project_runtime_value_for_publication(
    value: object,
    *,
    secret_values: Iterable[object] = (),
) -> Any:
    """Return a JSON-safe, redacted representation of runtime-only data."""
    return redact_sensitive_payload(
        _project_runtime_value(value),
        secret_values=secret_values,
    )


def project_diagnostic_for_publication(
    value: object,
    *,
    secret_values: Iterable[object] = (),
) -> dict[str, Any]:
    """生成可写入日志、诊断和事件流的脱敏对象。

    诊断不允许携带请求/响应正文，即使正文没有命中已知敏感值也必须
    作为结构字段隐藏；Debug 网络 Trace 不调用此投影，因此仍可保留原文。
    """
    projected = project_runtime_value_for_publication(
        value,
        secret_values=secret_values,
    )
    if not isinstance(projected, Mapping):
        return {"value": "<redacted>"}
    return _redact_diagnostic_mapping(projected)


def _redact_diagnostic_mapping(value: Mapping[object, object]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        name = str(key)
        normalized = name.strip().lower().replace("-", "_")
        if (
            normalized in {"body", "payload", "request", "response", "raw_body"}
            or normalized.endswith("_body")
        ):
            redacted[name] = "<redacted>"
        elif isinstance(item, Mapping):
            redacted[name] = _redact_diagnostic_mapping(item)
        elif isinstance(item, list):
            redacted[name] = [
                _redact_diagnostic_mapping(entry) if isinstance(entry, Mapping) else entry
                for entry in item
            ]
        else:
            redacted[name] = item
    return redacted


def project_runtime_plan_for_publication(runtime_plan: Mapping[str, object]) -> dict[str, Any]:
    """Expose plan structure while keeping executable configuration in memory only."""
    projected = _project_runtime_value(runtime_plan)
    if not isinstance(projected, dict):
        return {}
    raw_nodes = runtime_plan.get("executable_nodes")
    if not isinstance(raw_nodes, list):
        return projected

    public_nodes: list[dict[str, Any]] = []
    for raw_node in raw_nodes:
        if not isinstance(raw_node, Mapping):
            continue
        public_node = _project_runtime_value(
            {
                key: value
                for key, value in raw_node.items()
                if key != "node_config"
            }
        )
        if not isinstance(public_node, dict):
            continue
        raw_config = raw_node.get("node_config")
        public_node["node_config"] = _project_node_configuration(raw_config)
        public_nodes.append(public_node)
    projected["executable_nodes"] = public_nodes
    return projected


def _project_node_configuration(value: object) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {"configured_fields": [], "sensitive_fields": []}
    configured_fields = value.get("configured_fields")
    sensitive_fields = value.get("sensitive_fields")
    if isinstance(configured_fields, list) and isinstance(sensitive_fields, list):
        return {
            "configured_fields": sorted(
                item for item in configured_fields if isinstance(item, str)
            ),
            "sensitive_fields": sorted(
                item for item in sensitive_fields if isinstance(item, str)
            ),
        }
    configured_fields = sorted(str(key) for key in value)
    sensitive_fields = sorted(
        str(key)
        for key in value
        if _configuration_field_may_be_sensitive(str(key))
    )
    return {
        "configured_fields": configured_fields,
        "sensitive_fields": sensitive_fields,
    }


def _configuration_field_may_be_sensitive(field_name: str) -> bool:
    normalized = field_name.strip().lower().replace("-", "_")
    if normalized in _CONFIG_FIELDS_WITH_SENSITIVE_VALUES:
        return True
    return any(
        marker in normalized
        for marker in ("auth", "credential", "password", "secret", "token", "cookie", "key")
    )


def _project_runtime_value(value: object) -> Any:
    if isinstance(value, ResponseBodyRef):
        return {
            "kind": "network_response_body",
            "storage_kind": value.storage_kind,
            "size_bytes": value.size_bytes,
            "content_type": value.content_type,
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _project_runtime_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_project_runtime_value(item) for item in value]
    return value
