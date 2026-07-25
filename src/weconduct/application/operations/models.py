from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Mapping


class OperationRegistryError(ValueError):
    """稳定操作在校验或委托阶段产生的结构化错误。"""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        operation_id: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.operation_id = operation_id
        self.details = dict(details or {})


@dataclass(frozen=True)
class OperationDescriptor:
    """一个可版本化的宿主操作契约。"""

    operation_id: str
    contract_version: str = "1"
    input_schema: Mapping[str, object] = field(default_factory=dict)
    output_schema: Mapping[str, object] = field(default_factory=dict)
    required_permissions: tuple[str, ...] = ()
    side_effect_level: str = "read"
    audit_policy: str = "default"
    execution_mode: str = "sync"
    idempotency_capability: bool = False
    exposure: str = "stable_public"

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "contract_version": self.contract_version,
            "input_schema": deepcopy(dict(self.input_schema)),
            "output_schema": deepcopy(dict(self.output_schema)),
            "required_permissions": list(self.required_permissions),
            "side_effect_level": self.side_effect_level,
            "audit_policy": self.audit_policy,
            "execution_mode": self.execution_mode,
            "idempotency_capability": self.idempotency_capability,
            "exposure": self.exposure,
        }
