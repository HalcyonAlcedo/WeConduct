from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator


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


class OperationGetInput(OperationInputModel):
    operation_id: str = Field(min_length=1)


class ProjectCreateInput(OperationInputModel):
    project_name: str = Field(min_length=1)
    project_directory: str | None = None


class ProjectOpenInput(OperationInputModel):
    project_path: str = Field(min_length=1)


class ProjectSaveInput(OperationInputModel):
    graph_document: dict[str, Any] | None = None


class GraphCompileInput(OperationInputModel):
    graph_document: dict[str, Any] | None = None
    expected_revision: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def require_revision_for_external_graph_write(self) -> "GraphCompileInput":
        if self.graph_document is not None and self.expected_revision is None:
            raise ValueError("expected_revision is required when graph_document is provided")
        return self


class GraphGetInput(OperationInputModel):
    document_id: str | None = None


class GraphDocumentGetInput(OperationInputModel):
    document_id: str = Field(min_length=1)


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


class GraphDocumentReplaceInput(GraphDocumentInput):
    document_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def require_matching_document_id(self) -> "GraphDocumentReplaceInput":
        if self.graph_document.get("document_id") != self.document_id:
            raise ValueError("graph_document.document_id must match document_id")
        return self


class GraphNodeDraftBuildInput(OperationInputModel):
    resource_key: str = Field(min_length=1)
    node_id: str | None = None
    position: dict[str, Any] | None = None


class GraphContextInput(OperationInputModel):
    node_id: str = Field(min_length=1)
    depth: int = Field(default=1, ge=0, le=3)
    include_config: bool = False
    include_ports: bool = True
    max_nodes: int = Field(default=40, ge=1, le=200)
    max_edges: int = Field(default=80, ge=1, le=400)


class GraphPatchOperationInput(OperationInputModel):
    op: Literal["node.add", "node.update", "node.remove", "edge.add", "edge.remove"]
    resource_key: str | None = None
    node_id: str | None = None
    position: dict[str, Any] | None = None
    config_changes: dict[str, Any] | None = None
    changes: dict[str, Any] | None = None
    edge_id: str | None = None
    edge: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_operation_payload(self) -> "GraphPatchOperationInput":
        if self.op == "node.add":
            if not self.resource_key or not self.node_id:
                raise ValueError("node.add requires resource_key and node_id")
        elif self.op == "node.update":
            if not self.node_id or self.changes is None:
                raise ValueError("node.update requires node_id and changes")
        elif self.op == "node.remove":
            if not self.node_id:
                raise ValueError("node.remove requires node_id")
        elif self.op == "edge.add":
            if self.edge is None:
                raise ValueError("edge.add requires edge")
        elif self.op == "edge.remove" and not self.edge_id:
            raise ValueError("edge.remove requires edge_id")
        return self


class GraphPatchInput(OperationInputModel):
    expected_revision: int = Field(ge=0, strict=True)
    operations: list[GraphPatchOperationInput] = Field(min_length=1, max_length=100)


class ResourceCatalogueListInput(OperationInputModel):
    query: str | None = None
    tags: list[str] | None = None
    enabled: bool | None = None
    origin: str | None = None
    resource_type: str | None = None
    limit: int | None = Field(default=None, ge=1, le=200)


class GraphSourceProjectionInput(OperationInputModel):
    target_source_kind: Literal["native_flow"] = "native_flow"


class ResourceReferenceInput(OperationInputModel):
    resource_id: str = Field(min_length=1)


class ResourceSaveInput(OperationInputModel):
    resource_name: str = Field(min_length=1)
    replace_existing_resource_id: str | None = None
    tags: list[str] | None = None


class ResourceEnabledSetInput(ResourceReferenceInput):
    enabled: bool


class ResourceTagsSetInput(ResourceReferenceInput):
    tags: list[str]


class ResourceMetadataUpdateInput(ResourceReferenceInput):
    display_name: str = Field(min_length=1)
    description: str | None = None
    display_name_i18n: dict[str, str] | None = None
    description_i18n: dict[str, str] | None = None


class ResourceRenameInput(ResourceReferenceInput):
    display_name: str = Field(min_length=1)


class DebugSessionInput(OperationInputModel):
    session_id: str = Field(min_length=1)


class DebugHistoryProjectionInput(DebugSessionInput):
    event_index: int | None = Field(default=None, ge=0)
    keyframe_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_at_most_one_replay_selector(self) -> "DebugHistoryProjectionInput":
        if self.event_index is not None and self.keyframe_id is not None:
            raise ValueError("event_index and keyframe_id cannot be used together")
        return self


class DebugPauseInput(DebugSessionInput):
    reason: str = Field(min_length=1)
    node_id: str | None = None


class DebugAbortInput(DebugSessionInput):
    reason: str = Field(min_length=1)


class DebugVariablesApplyInput(DebugSessionInput):
    updates: dict[str, Any]
    apply_mode: str = "staged"


class DebugNodeDebuggerApplyInput(DebugSessionInput):
    node_id: str = Field(min_length=1)
    debugger: dict[str, Any]


class DebugParameterUnlockInput(DebugSessionInput):
    password: str = Field(min_length=1)


class ConfigurationScopeInput(OperationInputModel):
    scope: Literal["program", "project", "graph"]


class ConfigurationOperationsInput(ConfigurationScopeInput):
    operations: list[dict[str, Any]]
    confirm_high_risk: bool = False


class ExecutionStartInput(OperationInputModel):
    graph_document: dict[str, Any] | None = None


class ExecutionReferenceInput(OperationInputModel):
    execution_id: str = Field(min_length=1)


class ExecutionCancelInput(ExecutionReferenceInput):
    reason: str = "external api cancellation"


class ExecutionParameterUnlockInput(ExecutionReferenceInput):
    password: str = Field(min_length=1)


class PendingInputSubmitInput(ExecutionReferenceInput):
    request_id: str = Field(min_length=1)
    # 结构化类型校验由 PendingInputService 统一处理，保留数组/字符串等
    # 非对象载荷进入领域层，以便返回稳定的 invalid_payload 细节。
    values: Any


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
