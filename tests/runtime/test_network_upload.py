from __future__ import annotations

from concurrent.futures import Future

import httpx

from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.http_adapter import HttpxAdapter
from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_http_adapter_streams_upload_file_path(tmp_path) -> None:
    upload_path = tmp_path / "upload.bin"
    upload_path.write_bytes(b"streamed upload")
    received_payloads: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_payloads.append(request.content)
        return httpx.Response(201, request=request)

    adapter = HttpxAdapter(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    operation = NetworkOperation(
        operation_id="upload-1",
        session_id="session-1",
        method="PUT",
        url="https://example.test/upload",
        upload_file_path=upload_path,
    )

    result = adapter.execute(operation, NetworkContextSnapshot(context_id="context-1"))

    assert result.status == "succeeded"
    assert result.status_code == 201
    assert received_payloads == [b"streamed upload"]


def test_network_upload_passes_checked_file_path_to_network_runtime(tmp_path) -> None:
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
                    status_code=204,
                )
            )
            return future

    upload_path = tmp_path / "upload.txt"
    upload_path.write_text("payload", encoding="utf-8")
    service = StubNetworkRuntimeService()
    context = RuntimeContext(allowed_path_roots=(tmp_path,))
    node = {
        "node_id": "upload-1",
        "node_kind": "network.upload",
        "node_config": {
            "url": "https://example.test/upload",
            "method": "POST",
            "file_path": str(upload_path),
            "media_type": "text/plain",
        },
    }

    output = RuntimeExecutorRegistry(network_runtime_service=service).execute(
        "network.upload", node, context
    )

    assert output["status"] == "succeeded"
    assert output["uploaded_size"] == len(b"payload")
    assert service.operation is not None
    assert service.operation.upload_file_path == upload_path
    assert service.operation.headers["Content-Type"] == "text/plain"
