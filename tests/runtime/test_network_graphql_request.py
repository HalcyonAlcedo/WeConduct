from __future__ import annotations

from concurrent.futures import Future
import json

from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from weconduct.network_runtime.resources import ResponseBodyRef
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_network_graphql_request_returns_data_errors_and_extensions() -> None:
    class StubNetworkRuntimeService:
        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            future: Future[NetworkResult] = Future()
            payload = json.dumps(
                {"data": {"health": True}, "errors": [{"message": "partial"}], "extensions": {"trace": "x"}}
            ).encode("utf-8")
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                    body_ref=ResponseBodyRef(
                        session_id=operation.session_id,
                        storage_kind="memory",
                        size_bytes=len(payload),
                        content_type="application/json",
                        _payload=payload,
                    ),
                )
            )
            return future

    node = {
        "node_id": "graphql-1",
        "node_kind": "network.graphql_request",
        "node_config": {
            "endpoint": "https://example.test/graphql",
            "query": "query Health { health }",
            "variables": {},
        },
    }

    output = RuntimeExecutorRegistry(network_runtime_service=StubNetworkRuntimeService()).execute(
        "network.graphql_request", node, RuntimeContext()
    )

    assert output["status"] == "succeeded"
    assert output["data"] == {"health": True}
    assert output["errors"] == [{"message": "partial"}]
    assert output["extensions"] == {"trace": "x"}


def test_network_graphql_request_forwards_request_extensions() -> None:
    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.operation: NetworkOperation | None = None

        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            del snapshot
            self.operation = operation
            payload = b'{"data":{"health":true}}'
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                    body_ref=ResponseBodyRef(
                        session_id=operation.session_id,
                        storage_kind="memory",
                        size_bytes=len(payload),
                        content_type="application/json",
                        _payload=payload,
                    ),
                )
            )
            return future

    service = StubNetworkRuntimeService()
    output = RuntimeExecutorRegistry(network_runtime_service=service).execute(
        "network.graphql_request",
        {
            "node_id": "graphql-extensions",
            "node_kind": "network.graphql_request",
            "node_config": {
                "endpoint": "https://example.test/graphql",
                "query": "query Health { health }",
                "extensions": {"persistedQuery": {"version": 1}},
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert service.operation is not None
    assert json.loads(service.operation.content or b"{}") ["extensions"] == {
        "persistedQuery": {"version": 1}
    }


def test_network_graphql_subscription_is_rejected_in_0900() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.graphql_request",
        {
            "node_id": "subscription-node",
            "node_kind": "network.graphql_request",
            "node_config": {
                "endpoint": "https://example.test/graphql",
                "query": "subscription Watch { updates { id } }",
                "operation_name": "Watch",
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.graphql_subscription_not_supported"


def test_network_graphql_request_resolves_relative_endpoint_from_platform_default() -> None:
    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.operation: NetworkOperation | None = None

        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            del snapshot
            self.operation = operation
            payload = b'{"data":{"health":true}}'
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                    body_ref=ResponseBodyRef(
                        session_id=operation.session_id,
                        storage_kind="memory",
                        size_bytes=len(payload),
                        content_type="application/json",
                        _payload=payload,
                    ),
                )
            )
            return future

    service = StubNetworkRuntimeService()
    output = RuntimeExecutorRegistry(
        runtime_settings={"network_platform_defaults": {"base_url": "https://example.test/api/"}},
        network_runtime_service=service,
    ).execute(
        "network.graphql_request",
        {
            "node_id": "graphql-relative-endpoint",
            "node_kind": "network.graphql_request",
            "node_config": {"endpoint": "health", "query": "query Health { health }"},
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert service.operation is not None
    assert service.operation.url == "https://example.test/api/health"


def test_network_graphql_subscription_failure_exposes_structured_network_error() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.graphql_request",
        {
            "node_id": "graphql-subscription-invalid",
            "node_kind": "network.graphql_request",
            "node_config": {"action": "connect", "connection_id": "subscription-1"},
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.graphql_subscription_not_supported"
    assert output["network_error"]["request_id"] == output["request_id"]
    assert output["network_error"]["node_id"] == "graphql-subscription-invalid"
    assert output["network_error"]["details"] == {"action": "connect"}


def test_network_graphql_request_validation_failure_exposes_structured_network_error() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.graphql_request",
        {
            "node_id": "graphql-request-invalid",
            "node_kind": "network.graphql_request",
            "node_config": {"query": "query Health { health }"},
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.graphql_endpoint_required"
    assert output["network_error"]["request_id"] == output["request_id"]
    assert output["network_error"]["node_id"] == "graphql-request-invalid"
    assert output["network_error"]["network_context_id"] is None
