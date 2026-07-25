from __future__ import annotations

from concurrent.futures import Future

from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_network_batch_request_preserves_order_and_uses_bounded_executor() -> None:
    class StubNetworkRuntimeService:
        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                )
            )
            return future

    output = RuntimeExecutorRegistry(
        network_runtime_service=StubNetworkRuntimeService()
    ).execute(
        "network.batch_request",
        {
            "node_id": "batch-1",
            "node_kind": "network.batch_request",
            "node_config": {
                "requests": [
                    {"method": "GET", "url": "https://example.test/1"},
                    {"method": "POST", "url": "https://example.test/2", "body": {"n": 2}},
                ],
                "max_concurrency": 1,
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert [item["status_code"] for item in output["results"]] == [200, 200]
    assert output["succeeded_count"] == 2
    assert output["failed_count"] == 0


def test_network_batch_request_returns_item_failures_without_reordering() -> None:
    class StubNetworkRuntimeService:
        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            future: Future[NetworkResult] = Future()
            if operation.url.endswith("/bad"):
                future.set_result(
                    NetworkResult(
                        status="failed",
                        operation_id=operation.operation_id,
                        session_id=operation.session_id,
                        transport_error="network.connection_failed",
                    )
                )
            else:
                future.set_result(
                    NetworkResult(
                        status="succeeded",
                        operation_id=operation.operation_id,
                        session_id=operation.session_id,
                        status_code=201,
                    )
                )
            return future

    output = RuntimeExecutorRegistry(
        network_runtime_service=StubNetworkRuntimeService()
    ).execute(
        "network.batch_request",
        {
            "node_id": "batch-2",
            "node_kind": "network.batch_request",
            "node_config": {
                "requests": [
                    {"url": "https://example.test/good"},
                    {"url": "https://example.test/bad"},
                    {"url": "https://example.test/other"},
                ],
                "max_concurrency": 2,
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["results"][0]["status_code"] == 201
    assert output["results"][1]["error_code"] == "network.connection_failed"
    assert output["results"][2]["status_code"] == 201
    assert output["failed_count"] == 1


def test_network_batch_invalid_item_exposes_structured_network_error() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.batch_request",
        {
            "node_id": "batch-invalid-item",
            "node_kind": "network.batch_request",
            "node_config": {"requests": ["invalid item"]},
        },
        RuntimeContext(),
    )

    item = output["results"][0]
    assert output["status"] == "failed"
    assert item["error_code"] == "network.batch_item_invalid"
    assert item["network_error"]["request_id"] == item["request_id"]
    assert item["network_error"]["node_id"] == "batch-invalid-item:0"
