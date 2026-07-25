from __future__ import annotations

from concurrent.futures import Future
from hashlib import sha256

from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from weconduct.network_runtime.resources import ResponseBodyRef
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


class _WorkflowNetworkService:
    def __init__(self) -> None:
        self.calls: list[NetworkOperation] = []

    def submit(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
    ) -> Future[NetworkResult]:
        del snapshot
        self.calls.append(operation)
        response_body = (
            b'{"ok":true,"items":[1,2]}'
            if operation.response_storage == "auto"
            else b"download-payload"
        )
        future: Future[NetworkResult] = Future()
        future.set_result(
            NetworkResult(
                status="succeeded",
                operation_id=operation.operation_id,
                session_id=operation.session_id,
                status_code=200,
                headers={"Content-Type": "application/json"},
                body_ref=ResponseBodyRef(
                    session_id=operation.session_id,
                    storage_kind="memory",
                    size_bytes=len(response_body),
                    content_type="application/json",
                    _payload=response_body,
                ),
                final_url=operation.url,
            )
        )
        return future


def test_090_network_workflow_runs_request_assert_download_and_cleanup() -> None:
    service = _WorkflowNetworkService()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(network_runtime_service=service)

    response = registry.execute(
        "network.http_request",
        {
            "node_id": "workflow-http",
            "node_kind": "network.http_request",
            "node_config": {"url": "https://example.test/items", "method": "GET"},
        },
        context,
    )
    assert response["status"] == "succeeded"

    assertion = registry.execute(
        "network.response_assert",
        {
            "node_id": "workflow-assert",
            "node_kind": "network.response_assert",
            "node_config": {
                "expected_status_codes": [200],
                "required_headers": {"content-type": "application/json"},
                "body_contains": '"ok":true',
            },
        },
        context,
    )
    assert assertion["status"] == "succeeded"
    assert assertion["passed"] is True

    download = registry.execute(
        "network.download",
        {
            "node_id": "workflow-download",
            "node_kind": "network.download",
            "node_config": {"url": "https://example.test/archive", "method": "GET"},
        },
        context,
    )
    assert download["status"] == "succeeded"
    assert download["file_size"] == len(b"download-payload")
    assert download["checksum_sha256"] == sha256(b"download-payload").hexdigest()
    assert [call.response_storage for call in service.calls] == ["auto", "file"]

    context.close()
    assert context.browser_runtime == {}


def test_network_http_request_exposes_request_id_and_transport_error() -> None:
    class FailedNetworkService:
        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            del snapshot
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="failed",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    transport_error="network.connect_failed",
                )
            )
            return future

    output = RuntimeExecutorRegistry(network_runtime_service=FailedNetworkService()).execute(
        "network.http_request",
        {
            "node_id": "request-with-id",
            "node_kind": "network.http_request",
            "node_config": {"url": "https://example.test/unavailable", "method": "GET"},
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["request_id"].startswith("request-with-id-")
    assert output["transport_error"] == "network.connect_failed"
