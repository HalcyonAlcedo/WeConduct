from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import TYPE_CHECKING, Literal, Mapping
from uuid import uuid4

from .models import NetworkContextSnapshot

if TYPE_CHECKING:
    from weconduct.runtime.execution_context import ExecutionTokenContext


NetworkContextStrategy = Literal["inherit", "new", "anonymous", "fork", "switch", "reset"]


class UnknownNetworkContextError(ValueError):
    """Raised when a token refers to a context outside its execution session."""


@dataclass
class _NetworkContextRecord:
    context_id: str
    epoch: int
    parent_id: str | None = None
    branch_id: str | None = None
    values: dict[str, object] = field(default_factory=dict)


class NetworkContextRegistry:
    """Owns non-persistent network contexts for one or more execution sessions."""

    _MAPPING_VALUE_NAMES = frozenset(
        {"headers", "query", "cookies", "response_limits", "retry_policy"}
    )
    _VALUE_NAMES = frozenset(
        {
            "base_url",
            "headers",
            "query",
            "cookies",
            "auth",
            "tls",
            "proxy",
            "timeout_seconds",
            "response_limits",
            "retry_policy",
        }
    )

    def __init__(self, *, platform_defaults: Mapping[str, object] | None = None) -> None:
        self._lock = RLock()
        self._platform_defaults = self._normalize_values(platform_defaults or {})
        self._contexts_by_session: dict[str, dict[str, _NetworkContextRecord]] = {}

    def create(self, session_id: str, **values: object) -> ExecutionTokenContext:
        self._require_session_id(session_id)
        with self._lock:
            record = self._create_record(session_id, values=values)
            return self._to_token_context(record)

    def apply_strategy(
        self,
        session_id: str,
        token_context: ExecutionTokenContext,
        *,
        strategy: NetworkContextStrategy | str,
        overrides: Mapping[str, object] | None = None,
        switch_context_id: str | None = None,
    ) -> ExecutionTokenContext:
        self._require_session_id(session_id)
        normalized_strategy = self._normalize_strategy(strategy)
        normalized_overrides = self._normalize_values(overrides or {})
        with self._lock:
            if normalized_strategy == "inherit":
                record = self._resolve_record(session_id, token_context)
                return self._to_token_context(record)

            if normalized_strategy == "new":
                record = self._create_record(session_id, values=normalized_overrides)
                return self._to_token_context(record)

            if normalized_strategy == "anonymous":
                anonymous_values = self._strip_anonymous_values(normalized_overrides)
                record = self._create_record(session_id, values=anonymous_values)
                return self._to_token_context(record)

            if normalized_strategy == "fork":
                parent = self._resolve_record(session_id, token_context)
                values = self._merge_values(parent.values, normalized_overrides)
                record = self._create_record(
                    session_id,
                    values=values,
                    parent_id=parent.context_id,
                    branch_id=parent.branch_id or parent.context_id,
                    include_platform_defaults=False,
                )
                return self._to_token_context(record)

            if normalized_strategy == "switch":
                if not isinstance(switch_context_id, str) or not switch_context_id.strip():
                    raise ValueError("switch strategy requires switch_context_id")
                record = self._contexts_by_session.get(session_id, {}).get(switch_context_id)
                if record is None:
                    raise UnknownNetworkContextError(
                        f"network context is not registered in session: {switch_context_id}"
                    )
                if normalized_overrides:
                    self._apply_values(record, normalized_overrides)
                return self._to_token_context(record)

            record = self._resolve_record(session_id, token_context)
            record.values = self._build_initial_values(normalized_overrides)
            record.epoch += 1
            return self._to_token_context(record)

    def apply_overrides(
        self,
        session_id: str,
        token_context: ExecutionTokenContext,
        overrides: Mapping[str, object],
    ) -> ExecutionTokenContext:
        self._require_session_id(session_id)
        with self._lock:
            record = self._resolve_record(session_id, token_context)
            self._apply_values(record, self._normalize_values(overrides))
            return self._to_token_context(record)

    def snapshot(
        self,
        session_id: str,
        token_context: ExecutionTokenContext,
    ) -> NetworkContextSnapshot:
        self._require_session_id(session_id)
        with self._lock:
            record = self._resolve_record(session_id, token_context)
            values = deepcopy(record.values)
            return NetworkContextSnapshot(
                context_id=record.context_id,
                context_epoch=record.epoch,
                parent_id=record.parent_id,
                branch_id=record.branch_id,
                base_url=self._optional_str(values.get("base_url")),
                headers=self._string_mapping(values.get("headers")),
                query=self._string_mapping(values.get("query")),
                cookies=self._string_mapping(values.get("cookies")),
                auth=values.get("auth"),
                tls=values.get("tls"),
                proxy=values.get("proxy"),
                timeout_seconds=self._optional_positive_number(values.get("timeout_seconds")),
                response_limits=self._object_mapping(values.get("response_limits")),
                retry_policy=self._object_mapping(values.get("retry_policy")),
            )

    def clear_session(self, session_id: str) -> None:
        self._require_session_id(session_id)
        with self._lock:
            self._contexts_by_session.pop(session_id, None)

    def _create_record(
        self,
        session_id: str,
        *,
        values: Mapping[str, object],
        parent_id: str | None = None,
        branch_id: str | None = None,
        include_platform_defaults: bool = True,
    ) -> _NetworkContextRecord:
        context_id = f"network-context-{uuid4().hex}"
        record = _NetworkContextRecord(
            context_id=context_id,
            epoch=0,
            parent_id=parent_id,
            branch_id=branch_id,
            values=(
                self._build_initial_values(values)
                if include_platform_defaults
                else deepcopy(dict(values))
            ),
        )
        self._contexts_by_session.setdefault(session_id, {})[context_id] = record
        return record

    def _resolve_record(
        self,
        session_id: str,
        token_context: ExecutionTokenContext,
    ) -> _NetworkContextRecord:
        context_id = token_context.network_context_id
        if not isinstance(context_id, str) or not context_id.strip():
            raise UnknownNetworkContextError("execution token has no network context")
        record = self._contexts_by_session.get(session_id, {}).get(context_id)
        if record is None:
            raise UnknownNetworkContextError(
                f"network context is not registered in session: {context_id}"
            )
        return record

    def _build_initial_values(self, values: Mapping[str, object]) -> dict[str, object]:
        return self._merge_values(self._platform_defaults, values)

    def _apply_values(self, record: _NetworkContextRecord, values: Mapping[str, object]) -> None:
        record.values = self._merge_values(record.values, values)
        record.epoch += 1

    def _merge_values(
        self,
        base: Mapping[str, object],
        overrides: Mapping[str, object],
    ) -> dict[str, object]:
        merged = deepcopy(dict(base))
        for name, value in overrides.items():
            if name in self._MAPPING_VALUE_NAMES:
                existing_value = merged.get(name)
                existing_mapping = existing_value if isinstance(existing_value, Mapping) else {}
                override_mapping = value if isinstance(value, Mapping) else {}
                merged[name] = {**deepcopy(dict(existing_mapping)), **deepcopy(dict(override_mapping))}
            else:
                merged[name] = deepcopy(value)
        return merged

    def _normalize_values(self, values: Mapping[str, object]) -> dict[str, object]:
        normalized: dict[str, object] = {}
        for name, value in values.items():
            if name not in self._VALUE_NAMES:
                raise ValueError(f"unsupported network context value: {name}")
            if name in self._MAPPING_VALUE_NAMES:
                if not isinstance(value, Mapping):
                    raise ValueError(f"network context value must be a mapping: {name}")
                normalized[name] = deepcopy(dict(value))
            else:
                normalized[name] = deepcopy(value)
        return normalized

    def _strip_anonymous_values(self, values: Mapping[str, object]) -> dict[str, object]:
        anonymous_values = deepcopy(dict(values))
        anonymous_values.pop("auth", None)
        anonymous_values["cookies"] = {}
        headers = anonymous_values.get("headers")
        if isinstance(headers, Mapping):
            anonymous_values["headers"] = {
                name: value
                for name, value in headers.items()
                if not (isinstance(name, str) and name.lower() == "authorization")
            }
        return anonymous_values

    @staticmethod
    def _normalize_strategy(strategy: NetworkContextStrategy | str) -> NetworkContextStrategy:
        if strategy in {"inherit", "new", "anonymous", "fork", "switch", "reset"}:
            return strategy
        raise ValueError(f"unsupported network context strategy: {strategy}")

    @staticmethod
    def _to_token_context(record: _NetworkContextRecord) -> ExecutionTokenContext:
        from weconduct.runtime.execution_context import ExecutionTokenContext

        return ExecutionTokenContext(
            network_context_id=record.context_id,
            network_context_epoch=record.epoch,
        )

    @staticmethod
    def _require_session_id(session_id: str) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")

    @staticmethod
    def _optional_str(value: object) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _optional_positive_number(value: object) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
        return None

    @staticmethod
    def _string_mapping(value: object) -> Mapping[str, str]:
        if not isinstance(value, Mapping):
            return {}
        return {
            key: item
            for key, item in value.items()
            if isinstance(key, str) and isinstance(item, str)
        }

    @staticmethod
    def _object_mapping(value: object) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            return {}
        return {key: deepcopy(item) for key, item in value.items() if isinstance(key, str)}
