from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
from threading import Thread
from time import sleep

import pytest
import websockets

from tests.network_runtime.test_local_protocol_interop_090 import _write_local_mtls_certificates
from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.models import NetworkContextSnapshot
from weconduct.network_runtime.service import NetworkRuntimeService


@contextmanager
def _local_mtls_sse_server(tmp_path: Path):
    ca_file, server_cert_file, server_key_file, client_cert_file, client_key_file = (
        _write_local_mtls_certificates(tmp_path)
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"id: secure-event\ndata: secure-payload\n\n")
            self.wfile.flush()
            sleep(0.2)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=server_cert_file, keyfile=server_key_file)
    context.load_verify_locations(cafile=ca_file)
    context.verify_mode = ssl.CERT_REQUIRED
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            f"https://127.0.0.1:{server.server_port}/events",
            ca_file,
            server_cert_file,
            client_cert_file,
            client_key_file,
        )
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


def _certificate_pin(certificate_file: Path) -> str:
    certificate = ssl.PEM_cert_to_DER_cert(certificate_file.read_text(encoding="ascii"))
    return hashlib.sha256(certificate).hexdigest()


def _tls_snapshot(
    *,
    ca_file: Path,
    client_cert_file: Path,
    client_key_file: Path,
    certificate_pin: str,
) -> NetworkContextSnapshot:
    return NetworkContextSnapshot(
        context_id="long-connection-security",
        auth={"type": "bearer", "token": "long-connection-token"},
        tls={
            "verify": "custom_ca",
            "ca_file": str(ca_file),
            "client_cert_file": str(client_cert_file),
            "client_key_file": str(client_key_file),
            "certificate_pins": [certificate_pin],
        },
    )


def test_network_runtime_service_uses_mtls_pin_and_auth_for_sse(tmp_path: Path) -> None:
    with _local_mtls_sse_server(tmp_path) as (
        url,
        ca_file,
        server_cert_file,
        client_cert_file,
        client_key_file,
    ):
        service = NetworkRuntimeService(
            response_root_directory=tmp_path,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            handle, metadata = service.connect_sse(
                session_id="secure-sse",
                snapshot=_tls_snapshot(
                    ca_file=ca_file,
                    client_cert_file=client_cert_file,
                    client_key_file=client_key_file,
                    certificate_pin=_certificate_pin(server_cert_file),
                ),
                url=url,
            )
            event = handle.receive(timeout_seconds=2)
        finally:
            service.close()

    assert metadata["status_code"] == 200
    assert event["event_id"] == "secure-event"
    assert event["data"] == "secure-payload"


def test_network_runtime_service_rejects_sse_certificate_pin_mismatch(tmp_path: Path) -> None:
    with _local_mtls_sse_server(tmp_path) as (
        url,
        ca_file,
        _server_cert_file,
        client_cert_file,
        client_key_file,
    ):
        service = NetworkRuntimeService(
            response_root_directory=tmp_path,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            with pytest.raises(RuntimeError, match="network.tls_pin_mismatch"):
                service.connect_sse(
                    session_id="secure-sse-pin-mismatch",
                    snapshot=_tls_snapshot(
                        ca_file=ca_file,
                        client_cert_file=client_cert_file,
                        client_key_file=client_key_file,
                        certificate_pin="0" * 64,
                    ),
                    url=url,
                )
        finally:
            service.close()


def test_network_runtime_service_uses_mtls_pin_and_auth_for_websocket(tmp_path: Path) -> None:
    async def run() -> None:
        ca_file, server_cert_file, server_key_file, client_cert_file, client_key_file = (
            _write_local_mtls_certificates(tmp_path)
        )
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(certfile=server_cert_file, keyfile=server_key_file)
        server_context.load_verify_locations(cafile=ca_file)
        server_context.verify_mode = ssl.CERT_REQUIRED

        async def handler(connection) -> None:
            assert connection.request.headers["Authorization"] == "Bearer long-connection-token"
            await connection.send(f"ack:{await connection.recv()}")

        server = await websockets.serve(handler, "127.0.0.1", 0, ssl=server_context)
        port = server.sockets[0].getsockname()[1]
        service = NetworkRuntimeService(
            response_root_directory=tmp_path,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            handle, metadata = await asyncio.to_thread(
                service.connect_websocket,
                session_id="secure-websocket",
                snapshot=_tls_snapshot(
                    ca_file=ca_file,
                    client_cert_file=client_cert_file,
                    client_key_file=client_key_file,
                    certificate_pin=_certificate_pin(server_cert_file),
                ),
                url=f"wss://127.0.0.1:{port}/events",
            )
            await asyncio.to_thread(handle.send, "hello")
            received = await asyncio.to_thread(handle.receive, timeout_seconds=2)
        finally:
            service.close()
            server.close()
            await server.wait_closed()

        assert metadata["status"] == "connected"
        assert received == "ack:hello"

    asyncio.run(run())


def test_network_runtime_service_rejects_websocket_certificate_pin_mismatch(tmp_path: Path) -> None:
    async def run() -> None:
        ca_file, server_cert_file, server_key_file, client_cert_file, client_key_file = (
            _write_local_mtls_certificates(tmp_path)
        )
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(certfile=server_cert_file, keyfile=server_key_file)
        server_context.load_verify_locations(cafile=ca_file)
        server_context.verify_mode = ssl.CERT_REQUIRED

        async def handler(connection) -> None:
            await connection.wait_closed()

        server = await websockets.serve(handler, "127.0.0.1", 0, ssl=server_context)
        port = server.sockets[0].getsockname()[1]
        service = NetworkRuntimeService(
            response_root_directory=tmp_path,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            with pytest.raises(RuntimeError, match="network.tls_pin_mismatch"):
                await asyncio.to_thread(
                    service.connect_websocket,
                    session_id="secure-websocket-pin-mismatch",
                    snapshot=_tls_snapshot(
                        ca_file=ca_file,
                        client_cert_file=client_cert_file,
                        client_key_file=client_key_file,
                        certificate_pin="0" * 64,
                    ),
                    url=f"wss://127.0.0.1:{port}/events",
                )
        finally:
            service.close()
            server.close()
            await server.wait_closed()

    asyncio.run(run())
