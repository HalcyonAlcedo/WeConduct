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
