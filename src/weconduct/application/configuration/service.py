from __future__ import annotations

from copy import deepcopy
from typing import Any

from .registry import ConfigurationRegistry
from .repository import ConfigurationRepository
from .schema import ConfigField


class HighRiskConfigurationChangeRequiredError(ValueError):
    def __init__(self, *, scope: str, high_risk_changes: list[dict]) -> None:
        super().__init__("high-risk configuration changes require confirmation")
        self.scope = scope
        self.high_risk_changes = deepcopy(high_risk_changes)
        self.requires_confirmation = True


class ConfigurationService:
    def __init__(
        self,
        *,
        registry: ConfigurationRegistry,
        repositories: dict[str, ConfigurationRepository],
    ) -> None:
        self._registry = registry
        self._repositories = dict(repositories)

    def get_values(self, *, scope: str) -> dict:
        return {
            "scope": scope,
            "values": self._load_values(scope=scope),
        }

    def get_schema(self, *, scope: str) -> dict:
        fields_by_domain: dict[str, list[dict]] = {}
        for config_field in self._registry.fields_for_scope(scope):
            fields_by_domain.setdefault(config_field.domain, []).append(
                {
                    "key": config_field.key,
                    "type": config_field.field_type,
                    "default": deepcopy(config_field.default),
                    "risk_level": config_field.risk_level,
                    "status": config_field.status,
                    "editable": config_field.editable,
                }
            )
        return {
            "scope": scope,
            "domains": [
                {
                    "key": domain.key,
                    "label": domain.label,
                    "order": domain.order,
                    "fields": fields_by_domain.get(domain.key, []),
                }
                for domain in self._registry.domains_for_scope(scope)
            ],
        }

    def preview(self, *, scope: str, operations: list[dict]) -> dict:
        current_values = self._load_values(scope=scope)
        proposed_values = self._apply_operations(
            scope=scope,
            values=current_values,
            operations=operations,
        )
        high_risk_changes = self._collect_high_risk_changes(
            scope=scope,
            current_values=current_values,
            proposed_values=proposed_values,
        )
        return {
            "scope": scope,
            "current_values": current_values,
            "proposed_values": proposed_values,
            "confirmation_required": bool(high_risk_changes),
            "high_risk_changes": high_risk_changes,
        }

    def apply(
        self,
        *,
        scope: str,
        operations: list[dict],
        confirm_high_risk: bool = False,
    ) -> dict:
        preview = self.preview(scope=scope, operations=operations)
        if preview["confirmation_required"] and not confirm_high_risk:
            raise HighRiskConfigurationChangeRequiredError(
                scope=scope,
                high_risk_changes=preview["high_risk_changes"],
            )
        self._get_repository(scope).save(preview["proposed_values"])
        return {
            "scope": scope,
            "values": deepcopy(preview["proposed_values"]),
        }

    def reset(self, *, scope: str) -> dict:
        values = self._build_default_values(scope=scope)
        self._get_repository(scope).save(values)
        return {"scope": scope, "values": deepcopy(values)}

    def _get_repository(self, scope: str) -> ConfigurationRepository:
        repository = self._repositories.get(scope)
        if repository is None:
            raise ValueError(f"configuration scope not available: {scope}")
        return repository

    def _load_values(self, *, scope: str) -> dict:
        stored = self._get_repository(scope).load()
        values = self._build_default_values(scope=scope)
        for config_field in self._registry.fields_for_scope(scope):
            domain_values = stored.get(config_field.domain)
            if not isinstance(domain_values, dict) or config_field.key not in domain_values:
                continue
            value = domain_values[config_field.key]
            try:
                self._validate_value(config_field, value)
            except ValueError:
                continue
            values[config_field.domain][config_field.key] = deepcopy(value)
        return values

    def _build_default_values(self, *, scope: str) -> dict:
        self._get_repository(scope)
        values: dict[str, dict] = {}
        for config_field in self._registry.fields_for_scope(scope):
            values.setdefault(config_field.domain, {})[config_field.key] = deepcopy(
                config_field.default
            )
        return values

    def _apply_operations(self, *, scope: str, values: dict, operations: list[dict]) -> dict:
        if not isinstance(operations, list):
            raise ValueError("configuration operations must be a JSON array")
        next_values = deepcopy(values)
        for operation in operations:
            if not isinstance(operation, dict):
                raise ValueError("configuration operation must be a JSON object")
            operation_name = operation.get("op")
            path = operation.get("path")
            if not isinstance(operation_name, str) or operation_name not in {"add", "replace", "remove"}:
                raise ValueError("configuration operation op must be add, replace, or remove")
            if not isinstance(path, str):
                raise ValueError("configuration operation path must be a string")
            path_parts = self._parse_path(path)
            config_field = self._resolve_path_field(scope=scope, path_parts=path_parts)
            domain_values = next_values[config_field.domain]
            if len(path_parts) == 2:
                if operation_name == "remove":
                    raise ValueError("configuration field values cannot be removed")
                value = operation.get("value")
                self._validate_value(config_field, value)
                domain_values[config_field.key] = deepcopy(value)
                continue
            if config_field.field_type != "string_list":
                raise ValueError("configuration collection operation requires string_list field")
            items = domain_values[config_field.key]
            collection_index = self._resolve_collection_index(
                raw_index=path_parts[2],
                item_count=len(items),
                operation_name=operation_name,
            )
            if operation_name == "remove":
                items.pop(collection_index)
                continue
            item_value = operation.get("value")
            if not isinstance(item_value, str) or not item_value.strip():
                raise ValueError("configuration string_list item must be a non-empty string")
            if operation_name == "replace":
                items[collection_index] = item_value
            else:
                items.insert(collection_index, item_value)
        return next_values

    def _resolve_path_field(self, *, scope: str, path_parts: list[str]) -> ConfigField:
        if len(path_parts) not in {2, 3}:
            raise ValueError("configuration path must target a field or collection item")
        return self._registry.get_field(
            scope=scope,
            domain=path_parts[0],
            key=path_parts[1],
        )

    def _parse_path(self, path: str) -> list[str]:
        if not path.startswith("/"):
            raise ValueError("configuration path must start with /")
        parts = path.split("/")[1:]
        if not parts or any(not part for part in parts):
            raise ValueError("configuration path contains empty segment")
        return parts

    def _resolve_collection_index(
        self,
        *,
        raw_index: str,
        item_count: int,
        operation_name: str,
    ) -> int:
        if operation_name == "add" and raw_index == "-":
            return item_count
        try:
            index = int(raw_index)
        except ValueError as exc:
            raise ValueError("configuration collection index must be an integer") from exc
        maximum_index = item_count if operation_name == "add" else item_count - 1
        if index < 0 or index > maximum_index:
            raise ValueError("configuration collection index is out of range")
        return index

    def _validate_value(self, config_field: ConfigField, value: Any) -> None:
        if config_field.field_type == "boolean" and not isinstance(value, bool):
            raise ValueError(f"configuration field must be boolean: {config_field.key}")
        if config_field.field_type == "string" and not isinstance(value, str):
            raise ValueError(f"configuration field must be string: {config_field.key}")
        if config_field.field_type == "nullable_string" and value is not None and not isinstance(value, str):
            raise ValueError(f"configuration field must be string or null: {config_field.key}")
        if config_field.field_type == "integer" and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            raise ValueError(f"configuration field must be integer: {config_field.key}")
        if config_field.field_type == "float" and (
            not isinstance(value, (int, float)) or isinstance(value, bool)
        ):
            raise ValueError(f"configuration field must be a number: {config_field.key}")
        if config_field.field_type == "string_list" and (
            not isinstance(value, list)
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise ValueError(f"configuration field must be a string list: {config_field.key}")
        if config_field.field_type == "enum" and value not in config_field.options:
            raise ValueError(f"configuration field value is not allowed: {config_field.key}")
        if config_field.field_type == "object" and not isinstance(value, (dict, list)):
            raise ValueError(f"configuration field must be an object or array: {config_field.key}")

    def _collect_high_risk_changes(
        self,
        *,
        scope: str,
        current_values: dict,
        proposed_values: dict,
    ) -> list[dict]:
        changes: list[dict] = []
        for config_field in self._registry.fields_for_scope(scope):
            if config_field.risk_level != "high":
                continue
            before = current_values[config_field.domain][config_field.key]
            after = proposed_values[config_field.domain][config_field.key]
            if before != after:
                changes.append(
                    {
                        "path": f"/{config_field.domain}/{config_field.key}",
                        "from": deepcopy(before),
                        "to": deepcopy(after),
                    }
                )
        return changes
