from __future__ import annotations

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import ssl
from threading import Thread

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone
import websockets

from weconduct.application.sensitive_values.models import SensitiveConsumer
from weconduct.application.sensitive_values.service import SensitiveValueService
from weconduct.network_runtime.graphql_adapter import (
    GraphQLProtocolAdapter,
    GraphQLSubscriptionProtocol,
)
from weconduct.network_runtime.http_adapter import HttpxAdapter
from weconduct.network_runtime.long_connection import WebSocketClientHandle
from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation
from weconduct.network_runtime.oauth import OAuthService
from weconduct.network_runtime.access_policy import NetworkAccessPolicy


@contextmanager
def _local_http_proxy():
    observed: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            observed.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"proxied")

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", observed
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


@contextmanager
def _local_oauth_server():
    observed: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("content-length", "0"))
            observed["body"] = self.rfile.read(length).decode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"access_token": "local-access", "refresh_token": "local-refresh", "expires_in": 60}
                ).encode("utf-8")
            )

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/token", observed
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


def _write_local_ca_and_server_certificate(tmp_path: Path) -> tuple[Path, Path, Path]:
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "WeConduct local CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=True,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_file = tmp_path / "local-ca.pem"
    cert_file = tmp_path / "local-server.pem"
    key_file = tmp_path / "local-server.key"
    ca_file.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_file.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return ca_file, cert_file, key_file


@contextmanager
def _local_tls_server(tmp_path: Path):
    ca_file, cert_file, key_file = _write_local_ca_and_server_certificate(tmp_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"tls-ok")

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_port}", ca_file
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


def test_httpx_adapter_uses_local_http_proxy_without_direct_fallback(tmp_path: Path) -> None:
    with _local_http_proxy() as (proxy_url, observed):
        adapter = HttpxAdapter(response_root_directory=tmp_path, access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}))
        try:
            result = adapter.execute(
                NetworkOperation(operation_id="proxy-1", session_id="session-proxy", method="GET", url="http://example.test/resource"),
                NetworkContextSnapshot(context_id="context-proxy", proxy={"mode": "manual", "url": proxy_url}),
            )
        finally:
            adapter.close()

    assert result.status == "succeeded"
    assert result.status_code == 200
    assert observed == ["http://example.test/resource"]


def test_oauth_service_exchanges_against_local_token_endpoint_without_secret_leak(tmp_path: Path) -> None:
    with _local_oauth_server() as (token_url, observed):
        sensitive = SensitiveValueService()
        service = OAuthService(sensitive_values=sensitive)
        secret = sensitive.create("local-client-secret", scope_id="oauth-session", source="runtime_input")
        request = service.build_client_credentials_request(
            token_url=token_url,
            client_id="local-client",
            client_secret=secret,
            scope="read",
            scope_id="oauth-session",
        )
        state = service.exchange_client_credentials(request=request, scope_id="oauth-session")

    assert "local-client-secret" not in observed["body"]
    assert sensitive.resolve(state.access_token, consumer=SensitiveConsumer.NETWORK_RUNTIME) == "local-access"


def test_httpx_adapter_uses_local_custom_ca(tmp_path: Path) -> None:
    with _local_tls_server(tmp_path) as (base_url, ca_file):
        adapter = HttpxAdapter(
            response_root_directory=tmp_path,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            result = adapter.execute(
                NetworkOperation(operation_id="tls-1", session_id="session-tls", method="GET", url=f"{base_url}/ok"),
                NetworkContextSnapshot(context_id="context-tls", tls={"verify": "custom_ca", "ca_file": str(ca_file)}),
            )
        finally:
            adapter.close()

    assert result.status == "succeeded"
    assert result.status_code == 200


def test_graphql_subscription_uses_local_websocket_protocol() -> None:
    from threading import Event

    ready = Event()
    stop = Event()
    server_info: dict[str, object] = {}

    async def handler(socket) -> None:
        await socket.recv()
        await socket.send(json.dumps({"type": "connection_ack"}))
        subscribe = json.loads(await socket.recv())
        await socket.send(json.dumps({"id": subscribe["id"], "type": "next", "payload": {"data": {"tick": 1}}}))
        await socket.send(json.dumps({"id": subscribe["id"], "type": "complete"}))

    def server_thread() -> None:
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)

        async def run_server() -> None:
            server = await websockets.serve(handler, "127.0.0.1", 0)
            server_info["server"] = server
            server_info["port"] = server.sockets[0].getsockname()[1]
            ready.set()
            while not stop.is_set():
                await asyncio.sleep(0.01)
            server.close()
            await server.wait_closed()

        try:
            loop.run_until_complete(run_server())
        finally:
            loop.close()

    thread = Thread(target=server_thread, daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    port = int(server_info["port"])
    handle = WebSocketClientHandle(
        url=f"ws://127.0.0.1:{port}",
        subprotocols=["graphql-transport-ws"],
    )
    try:
        adapter = GraphQLProtocolAdapter()
        request = adapter.build_subscription(
            endpoint=f"http://127.0.0.1:{port}",
            query="subscription Tick { tick }",
            session_id="graphql-session",
        )
        handle.start()
        handle.send(json.dumps(GraphQLSubscriptionProtocol.connection_init()))
        assert GraphQLSubscriptionProtocol.parse(handle.receive()).type == "connection_ack"
        handle.send(json.dumps(GraphQLSubscriptionProtocol.subscribe(request_id="1", request=request)))
        next_frame = GraphQLSubscriptionProtocol.parse(handle.receive())
        complete_frame = GraphQLSubscriptionProtocol.parse(handle.receive())
        assert next_frame.type == "next"
        assert next_frame.payload == {"data": {"tick": 1}}
        assert complete_frame.type == "complete"
    finally:
        handle.close()
        stop.set()
        thread.join(timeout=2)
