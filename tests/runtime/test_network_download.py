from __future__ import annotations

from concurrent.futures import Future
from hashlib import sha256

from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from weconduct.network_runtime.resources import ResponseBodyRef
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_network_download_requests_file_backed_response_and_returns_metadata() -> None:
    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.operation: NetworkOperation | None = None

        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            self.operation = operation
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                    final_url="https://example.test/final",
                    body_ref=ResponseBodyRef(
                        session_id=operation.session_id,
                        storage_kind="memory",
                        size_bytes=8,
                        content_type="application/octet-stream",
                        _payload=b"download",
                    ),
                )
            )
            return future

    service = StubNetworkRuntimeService()
    node = {
        "node_id": "download-1",
        "node_kind": "network.download",
        "node_config": {"url": "https://example.test/file", "method": "GET"},
    }

    output = RuntimeExecutorRegistry(network_runtime_service=service).execute(
        "network.download", node, RuntimeContext()
    )

    assert service.operation is not None
    assert service.operation.response_storage == "file"
    assert output["status"] == "succeeded"
    assert output["file_size"] == 8
    assert output["media_type"] == "application/octet-stream"
    assert output["checksum_sha256"] == sha256(b"download").hexdigest()
    assert output["final_url"] == "https://example.test/final"
