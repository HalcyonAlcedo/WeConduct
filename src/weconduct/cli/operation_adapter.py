from __future__ import annotations

from typing import Mapping

from weconduct.application.operations import (
    HostOperationService,
    OperationCaller,
    OperationDescriptor,
)


class CliOperationAdapter:
    """把 CLI 参数适配为受限的稳定宿主操作调用。"""

    _CALLER = OperationCaller(
        caller_id="cli:local",
        permissions=frozenset({"operation.invoke"}),
    )

    def __init__(self, operation_service: HostOperationService) -> None:
        self._operation_service = operation_service

    def invoke(
        self,
        operation_id: str,
        payload: Mapping[str, object],
        *,
        idempotency_key: str | None = None,
    ) -> tuple[OperationDescriptor, dict[str, object]]:
        descriptor = self._operation_service.describe(operation_id)
        result = self._operation_service.invoke(
            operation_id,
            payload,
            caller=self._CALLER,
            idempotency_key=idempotency_key,
        )
        return descriptor, result
