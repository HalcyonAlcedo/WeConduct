from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import select
import socket
import socketserver
import ssl
from threading import Thread

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import RequestReceived, StreamEnded
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
from weconduct.network_runtime.service import NetworkRuntimeService


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
def _local_http_target():
    observed: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            observed.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"socks-ok")

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
def _local_socks5_proxy():
    observed: list[tuple[str, int]] = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            client = self.request
            version, method_count = _recv_exact(client, 2)
            if version != 5:
                return
            _recv_exact(client, method_count)
            client.sendall(b"\x05\x00")

            version, command, _reserved, address_type = _recv_exact(client, 4)
            if version != 5 or command != 1:
                client.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            if address_type == 1:
                host = socket.inet_ntoa(_recv_exact(client, 4))
            elif address_type == 3:
                size = _recv_exact(client, 1)[0]
                host = _recv_exact(client, size).decode("idna")
            elif address_type == 4:
                host = socket.inet_ntop(socket.AF_INET6, _recv_exact(client, 16))
            else:
                client.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            port = int.from_bytes(_recv_exact(client, 2), "big")
            observed.append((host, port))
            try:
                upstream = socket.create_connection((host, port), timeout=2)
            except OSError:
                client.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            with upstream:
                client.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
                _relay_bidirectionally(client, upstream)

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Server(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"socks5://127.0.0.1:{server.server_address[1]}", observed
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("SOCKS5 peer closed during handshake")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _relay_bidirectionally(left: socket.socket, right: socket.socket) -> None:
    left.settimeout(2)
    right.settimeout(2)
    sockets = [left, right]
    while True:
        readable, _, _ = select.select(sockets, [], [], 0.2)
        if not readable:
            continue
        for source in readable:
            target = right if source is left else left
            try:
                data = source.recv(65536)
            except (TimeoutError, socket.timeout):
                continue
            if not data:
                return
            target.sendall(data)


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


def _write_local_mtls_certificates(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "WeConduct local mTLS CA")])
    now = datetime.now(timezone.utc)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
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

    def issue_certificate(
        *,
        common_name: str,
        usages: list[x509.ObjectIdentifier],
        san: x509.SubjectAlternativeName | None = None,
    ) -> tuple[object, x509.Certificate]:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        builder = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage(usages), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        )
        if san is not None:
            builder = builder.add_extension(san, critical=False)
        return key, builder.sign(ca_key, hashes.SHA256())

    server_key, server_cert = issue_certificate(
        common_name="127.0.0.1",
        usages=[x509.ExtendedKeyUsageOID.SERVER_AUTH],
        san=x509.SubjectAlternativeName(
            [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
        ),
    )
    client_key, client_cert = issue_certificate(
        common_name="WeConduct local client",
        usages=[x509.ExtendedKeyUsageOID.CLIENT_AUTH],
    )

    def write_key(path: Path, key: object) -> None:
        path.write_bytes(
            key.private_bytes(  # type: ignore[attr-defined]
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )

    ca_file = tmp_path / "mtls-ca.pem"
    server_cert_file = tmp_path / "mtls-server.pem"
    server_key_file = tmp_path / "mtls-server.key"
    client_cert_file = tmp_path / "mtls-client.pem"
    client_key_file = tmp_path / "mtls-client.key"
    ca_file.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    server_cert_file.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    client_cert_file.write_bytes(client_cert.public_bytes(serialization.Encoding.PEM))
    write_key(server_key_file, server_key)
    write_key(client_key_file, client_key)
    return ca_file, server_cert_file, server_key_file, client_cert_file, client_key_file


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
        yield f"https://127.0.0.1:{server.server_address[1]}", ca_file
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


@contextmanager
def _local_mtls_server(tmp_path: Path):
    ca_file, cert_file, key_file, client_cert_file, client_key_file = _write_local_mtls_certificates(tmp_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"mtls-ok")

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    context.load_verify_locations(cafile=ca_file)
    context.verify_mode = ssl.CERT_REQUIRED
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_port}", ca_file, client_cert_file, client_key_file
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


@contextmanager
def _local_http2_server(tmp_path: Path):
    ca_file, cert_file, key_file = _write_local_ca_and_server_certificate(tmp_path)

    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            tls_socket: ssl.SSLSocket | None = None
            try:
                tls_socket = context.wrap_socket(self.request, server_side=True)
                connection = H2Connection(
                    config=H2Configuration(client_side=False, header_encoding="utf-8")
                )
                connection.initiate_connection()
                tls_socket.sendall(connection.data_to_send())
                while True:
                    data = tls_socket.recv(65535)
                    if not data:
                        return
                    for event in connection.receive_data(data):
                        if isinstance(event, RequestReceived):
                            continue
                        if isinstance(event, StreamEnded):
                            connection.send_headers(
                                event.stream_id,
                                [(":status", "200"), ("content-type", "text/plain")],
                                end_stream=False,
                            )
                            connection.send_data(event.stream_id, b"http2-ok", end_stream=True)
                    tls_socket.sendall(connection.data_to_send())
            except (OSError, ssl.SSLError):
                return
            finally:
                if tls_socket is not None:
                    try:
                        tls_socket.close()
                    except OSError:
                        pass

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.set_alpn_protocols(["h2"])
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    server = Server(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_address[1]}", ca_file
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

    assert result.status == "succeeded", result.transport_error
    assert result.status_code == 200
    assert observed == ["http://example.test/resource"]


def test_httpx_adapter_forwards_through_real_local_socks5_proxy(tmp_path: Path) -> None:
    with _local_http_target() as (target_url, target_observed):
        with _local_socks5_proxy() as (proxy_url, proxy_observed):
            adapter = HttpxAdapter(
                response_root_directory=tmp_path,
                access_policy=NetworkAccessPolicy(allow_loopback=True),
            )
            try:
                result = adapter.execute(
                    NetworkOperation(
                        operation_id="socks-1",
                        session_id="session-socks",
                        method="GET",
                        url=f"{target_url}/resource",
                    ),
                    NetworkContextSnapshot(
                        context_id="context-socks",
                        proxy={"mode": "manual", "url": proxy_url},
                    ),
                )
            finally:
                adapter.close()

    assert result.status == "succeeded", result.transport_error
    assert result.status_code == 200
    assert target_observed == ["/resource"]
    assert proxy_observed == [("127.0.0.1", int(target_url.rsplit(":", 1)[1]))]


def test_oauth_service_exchanges_against_local_token_endpoint_without_secret_leak(tmp_path: Path) -> None:
    with _local_oauth_server() as (token_url, observed):
        sensitive = SensitiveValueService()
        service = OAuthService(
            sensitive_values=sensitive,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
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


def test_oauth_service_refreshes_against_local_token_endpoint(tmp_path: Path) -> None:
    with _local_oauth_server() as (token_url, observed):
        sensitive = SensitiveValueService()
        service = OAuthService(
            sensitive_values=sensitive,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        refresh_ref = sensitive.create("local-refresh-secret", scope_id="oauth-refresh", source="runtime_input")
        state = service.refresh_access_token(
            token_url=token_url,
            refresh_token=refresh_ref,
            scope_id="oauth-refresh",
            client_id="local-client",
            scope="read",
        )

    assert "grant_type=refresh_token" in observed["body"]
    assert "local-refresh-secret" in observed["body"]
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


def test_httpx_adapter_enforces_local_tls_certificate_pins(tmp_path: Path) -> None:
    with _local_tls_server(tmp_path) as (base_url, ca_file):
        server_der = ssl.PEM_cert_to_DER_cert((tmp_path / "local-server.pem").read_text(encoding="ascii"))
        matching_pin = hashlib.sha256(server_der).hexdigest()
        adapter = HttpxAdapter(
            response_root_directory=tmp_path,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            matching = adapter.execute(
                NetworkOperation(operation_id="tls-pin-match", session_id="session-tls-pin", method="GET", url=f"{base_url}/ok"),
                NetworkContextSnapshot(
                    context_id="context-tls-pin-match",
                    tls={
                        "verify": "custom_ca",
                        "ca_file": str(ca_file),
                        "certificate_pins": [matching_pin],
                    },
                ),
            )
            mismatching = adapter.execute(
                NetworkOperation(operation_id="tls-pin-mismatch", session_id="session-tls-pin", method="GET", url=f"{base_url}/ok"),
                NetworkContextSnapshot(
                    context_id="context-tls-pin-mismatch",
                    tls={
                        "verify": "custom_ca",
                        "ca_file": str(ca_file),
                        "certificate_pins": ["0" * 64],
                    },
                ),
            )
        finally:
            adapter.close()

    assert matching.status == "succeeded", matching.transport_error
    assert mismatching.status == "failed"
    assert mismatching.transport_error == "network.tls_pin_mismatch"


def test_httpx_adapter_uses_local_mtls_certificate(tmp_path: Path) -> None:
    with _local_mtls_server(tmp_path) as (base_url, ca_file, client_cert_file, client_key_file):
        adapter = HttpxAdapter(
            response_root_directory=tmp_path,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            result = adapter.execute(
                NetworkOperation(operation_id="mtls-1", session_id="session-mtls", method="GET", url=f"{base_url}/ok"),
                NetworkContextSnapshot(
                    context_id="context-mtls",
                    tls={
                        "verify": "custom_ca",
                        "ca_file": str(ca_file),
                        "client_cert_file": str(client_cert_file),
                        "client_key_file": str(client_key_file),
                    },
                ),
            )
        finally:
            adapter.close()

    assert result.status == "succeeded", result.transport_error
    assert result.status_code == 200


def test_httpx_adapter_negotiates_http2_against_local_alpn_server(tmp_path: Path) -> None:
    with _local_http2_server(tmp_path) as (base_url, ca_file):
        adapter = HttpxAdapter(
            response_root_directory=tmp_path,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            result = adapter.execute(
                NetworkOperation(operation_id="http2-1", session_id="session-http2", method="GET", url=f"{base_url}/ok"),
                NetworkContextSnapshot(
                    context_id="context-http2",
                    tls={"verify": "custom_ca", "ca_file": str(ca_file)},
                ),
            )
        finally:
            adapter.close()

    assert result.status == "succeeded", result.transport_error
    assert result.status_code == 200
    assert result.body_ref is not None


def test_network_runtime_service_enables_http2_on_its_default_client(tmp_path: Path) -> None:
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allow_loopback=True),
    )
    try:
        assert service._client._transport._pool._http2 is True  # type: ignore[attr-defined]
    finally:
        service.close()


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
        access_policy=NetworkAccessPolicy(allow_loopback=True),
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
