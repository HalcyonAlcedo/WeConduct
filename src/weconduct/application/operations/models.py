from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator


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


class OperationInputModel(BaseModel):
    """稳定操作的输入基类，拒绝未声明字段。"""

    model_config = ConfigDict(extra="forbid")


class PublicOperationOutput(BaseModel):
    """已由宿主过滤的公开对象输出。"""

    model_config = ConfigDict(extra="forbid")


def build_public_output_model(
    name: str,
    fields: frozenset[str],
) -> type[PublicOperationOutput]:
    """构造只承认 descriptor 明确字段的稳定公开输出模型。"""
    return create_model(
        name,
        __base__=PublicOperationOutput,
        **{field_name: (Any | None, None) for field_name in sorted(fields)},
    )


class EmptyOperationInput(OperationInputModel):
    pass


class ProjectCreateInput(OperationInputModel):
    project_name: str = Field(min_length=1)
    project_directory: str | None = None


class ProjectOpenInput(OperationInputModel):
    project_path: str = Field(min_length=1)


class ProjectSaveInput(OperationInputModel):
    graph_document: dict[str, Any] | None = None


class GraphGetInput(OperationInputModel):
    document_id: str | None = None


class GraphDocumentInput(OperationInputModel):
    graph_document: dict[str, Any]


class GraphReplaceInput(GraphDocumentInput):
    expected_revision: int = Field(ge=0, strict=True)

    @field_validator("graph_document")
    @classmethod
    def reject_non_workspace_document(cls, graph_document: dict[str, Any]) -> dict[str, Any]:
        document_id = graph_document.get("document_id")
        if document_id is not None and document_id != "graph:workspace":
            raise ValueError("graph.replace only supports the workspace graph")
        return graph_document


class GraphNodeDraftBuildInput(OperationInputModel):
    resource_key: str = Field(min_length=1)
    node_id: str | None = None
    position: dict[str, Any] | None = None


class ExecutionStartInput(OperationInputModel):
    graph_document: dict[str, Any] | None = None


class ExecutionReferenceInput(OperationInputModel):
    execution_id: str = Field(min_length=1)


class ExecutionCancelInput(ExecutionReferenceInput):
    reason: str = "external api cancellation"


class PendingInputSubmitInput(ExecutionReferenceInput):
    request_id: str = Field(min_length=1)
    values: dict[str, Any]


class SideEffectLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class AuditPolicy(StrEnum):
    NONE = "none"
    REQUIRED = "required"


class IdempotencyCapability(StrEnum):
    UNSUPPORTED = "unsupported"
    SUPPORTED = "supported"


class OperationExposure(StrEnum):
    STABLE_PUBLIC = "stable_public"
    MANAGED_PLUGIN = "managed_plugin"
    INTERNAL = "internal"


@dataclass(frozen=True)
class OperationCaller:
    """调用方身份只由受信任 adapter 构造，不能来自 operation 输入。"""

    caller_id: str
    permissions: frozenset[str]


@dataclass(frozen=True)
class OperationAuditRecord:
    operation_id: str
    caller_id: str
    outcome: Literal["succeeded", "rejected", "failed"]
    input_summary: Mapping[str, object]


class InMemoryOperationAuditTrail:
    """进程内的有限审计记录，用于桌面宿主和测试。"""

    def __init__(self, *, limit: int = 1_000) -> None:
        self._limit = limit
        self.records: list[OperationAuditRecord] = []

    def append(self, record: OperationAuditRecord) -> None:
        self.records.append(record)
        if len(self.records) > self._limit:
            del self.records[: len(self.records) - self._limit]


class InMemoryOperationIdempotencyStore:
    """以 caller、operation 和客户端键隔离的进程内重放缓存。"""

    def __init__(self, *, limit: int = 1_000) -> None:
        self._limit = limit
        self._lock = RLock()
        self._entries: dict[tuple[str, str, str], dict[str, object] | None] = {}

    def reserve_or_replay(
        self,
        *,
        caller_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> dict[str, object] | None:
        key = (caller_id, operation_id, idempotency_key)
        with self._lock:
            if key not in self._entries:
                self._entries[key] = None
                self._trim_completed_entries()
                return None
            result = self._entries[key]
            if result is None:
                raise OperationRegistryError(
                    "operation.in_progress",
                    "an identical operation is already in progress",
                    operation_id=operation_id,
                )
            return deepcopy(result)

    def complete(
        self,
        *,
        caller_id: str,
        operation_id: str,
        idempotency_key: str,
        result: Mapping[str, object],
    ) -> None:
        key = (caller_id, operation_id, idempotency_key)
        with self._lock:
            if key in self._entries:
                self._entries[key] = deepcopy(dict(result))
                self._trim_completed_entries()

    def release(
        self,
        *,
        caller_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> None:
        with self._lock:
            self._entries.pop((caller_id, operation_id, idempotency_key), None)

    def _trim_completed_entries(self) -> None:
        while len(self._entries) > self._limit:
            completed_key = next(
                (key for key, result in self._entries.items() if result is not None),
                None,
            )
            if completed_key is None:
                return
            self._entries.pop(completed_key)


class OperationInvocationResult(dict[str, object]):
    """公开操作结果及其传输层可消费的幂等重放状态。"""

    def __init__(self, value: Mapping[str, object], *, replayed: bool) -> None:
        super().__init__(value)
        self.replayed = replayed


@dataclass(frozen=True)
class OperationDescriptor:
    """一个可版本化的宿主操作契约。"""

    operation_id: str
    contract_version: str = "1"
    input_model: type[BaseModel] = EmptyOperationInput
    output_model: type[BaseModel] = PublicOperationOutput
    output_fields: frozenset[str] = frozenset()
    required_permissions: frozenset[str] = frozenset({"operation.invoke"})
    side_effect_level: SideEffectLevel = SideEffectLevel.READ
    audit_policy: AuditPolicy = AuditPolicy.REQUIRED
    execution_mode: Literal["sync", "async"] = "sync"
    idempotency_capability: IdempotencyCapability = IdempotencyCapability.UNSUPPORTED
    exposure: OperationExposure = OperationExposure.STABLE_PUBLIC

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "contract_version": self.contract_version,
            "input_schema": deepcopy(self.input_model.model_json_schema()),
            "output_schema": deepcopy(self.output_model.model_json_schema()),
            "required_permissions": list(self.required_permissions),
            "side_effect_level": self.side_effect_level.value,
            "audit_policy": self.audit_policy.value,
            "execution_mode": self.execution_mode,
            "idempotency_capability": self.idempotency_capability.value,
            "exposure": self.exposure.value,
        }
