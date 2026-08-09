from __future__ import annotations

from concurrent.futures import Future

import httpx

from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.http_adapter import HttpxAdapter
from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from weconduct.network_runtime.resources import ResponseBodyRef
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
        upload_allowed_roots=(tmp_path,),
    )

    result = adapter.execute(operation, NetworkContextSnapshot(context_id="context-1"))

    assert result.status == "succeeded"
    assert result.status_code == 201
    assert received_payloads == [b"streamed upload"]


def test_http_adapter_rejects_upload_file_path_without_explicit_allowed_root(tmp_path) -> None:
    upload_path = tmp_path / "private-upload.bin"
    upload_path.write_bytes(b"must not leave this machine")
    handler_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal handler_called
        handler_called = True
        return httpx.Response(201, request=request)

    adapter = HttpxAdapter(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    result = adapter.execute(
        NetworkOperation(
            operation_id="upload-untrusted-path",
            session_id="upload-untrusted-session",
            method="PUT",
            url="https://example.test/upload",
            upload_file_path=upload_path,
        ),
        NetworkContextSnapshot(context_id="upload-untrusted-context"),
    )

    assert handler_called is False
    assert result.status == "failed"
    assert result.transport_error == "network.upload_path_denied"


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
    assert tmp_path.resolve() in service.operation.upload_allowed_roots
    assert service.operation.headers["Content-Type"] == "text/plain"


def test_network_upload_accepts_session_body_ref_with_multipart_and_checksum() -> None:
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
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=201,
                )
            )
            return future

    payload = b"session-upload-payload"
    service = StubNetworkRuntimeService()
    node = {
        "node_id": "upload-session-ref",
        "node_kind": "network.upload",
        "node_config": {
            "url": "https://example.test/upload",
            "method": "POST",
            "source": ResponseBodyRef(
                session_id="runtime-context",
                storage_kind="memory",
                size_bytes=len(payload),
                content_type="application/octet-stream",
                _payload=payload,
            ),
            "field_name": "artifact",
            "multipart": True,
            "multipart_fields": {"purpose": "test"},
            "media_type": "application/octet-stream",
            "checksum_sha256": "9d458e4d0537b4777e8dd5d87b34012cb8d4472f88dbded0c9c0ddad1b7afacb",
            "max_upload_bytes": len(payload),
        },
    }

    output = RuntimeExecutorRegistry(network_runtime_service=service).execute(
        "network.upload",
        node,
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert output["uploaded_size"] == len(payload)
    assert output["source_checksum_sha256"] == node["node_config"]["checksum_sha256"]
    assert service.operation is not None
    assert service.operation.upload_file_path is None
    assert service.operation.headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert service.operation.upload_stream is not None
