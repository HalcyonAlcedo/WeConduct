from __future__ import annotations

from concurrent.futures import Future

from weconduct.network_runtime.errors import build_network_error
from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from weconduct.application.sensitive_values.service import SensitiveValueService
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_http_request_node_preserves_structured_network_failure() -> None:
    class _NetworkRuntimeService:
        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            future: Future[NetworkResult] = Future()
            error = build_network_error(
                "network.timeout",
                operation=operation,
                snapshot=snapshot,
            )
            future.set_result(
                NetworkResult(
                    status="failed",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    transport_error=error.error_code,
                    error=error,
                )
            )
            return future

        def cancel_session(self, _session_id: str) -> None:
            pass

    output = RuntimeExecutorRegistry(
        network_runtime_service=_NetworkRuntimeService()
    ).execute(
        "network.http_request",
        {
            "node_id": "http-structured-error",
            "node_kind": "network.http_request",
            "node_config": {
                "method": "GET",
                "url": "https://example.test/resource",
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.timeout"
    assert output["network_error"] == {
        "error_code": "network.timeout",
        "message": "network.timeout",
        "details": {},
        "request_id": output["request_id"],
        "node_id": "http-structured-error",
        "network_context_id": output["network_error"]["network_context_id"],
        "retry_attempt": 1,
    }


def test_runtime_executor_passes_sensitive_service_to_owned_network_runtime() -> None:
    sensitive_values = SensitiveValueService()
    context = RuntimeContext()
    context.flow_runtime["sensitive_value_service"] = sensitive_values
    registry = RuntimeExecutorRegistry()

    service = registry._resolve_network_runtime_service(context)  # type: ignore[attr-defined]
    try:
        assert service._sensitive_values is sensitive_values  # type: ignore[attr-defined]
    finally:
        context.close()


def test_runtime_executor_passes_network_audit_sink_to_owned_network_runtime() -> None:
    audit_events: list[tuple[str, dict[str, object]]] = []
    audit_sink = lambda event_name, payload: audit_events.append((event_name, payload))
    context = RuntimeContext(flow_runtime={"network_audit_event_sink": audit_sink})
    registry = RuntimeExecutorRegistry()

    service = registry._resolve_network_runtime_service(context)  # type: ignore[attr-defined]
    try:
        assert service._audit_event_sink is audit_sink  # type: ignore[attr-defined]
        assert audit_events == []
    finally:
        context.close()
