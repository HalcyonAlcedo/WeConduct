from __future__ import annotations

import asyncio
import socket

import httpcore
import httpx
import pytest

from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.transport import (
    PinnedDnsAsyncHTTPTransport,
    ValidatedNetworkBackend,
    _PinnedDnsAsyncTunnelHTTPConnection,
    _resolve_tunnel_sni_hostname,
)


def test_network_access_policy_blocks_loopback_by_default() -> None:
    policy = NetworkAccessPolicy()

    with pytest.raises(ValueError, match="network.access_denied"):
        policy.validate_url("http://127.0.0.1:8080/status")


def test_network_access_policy_allows_explicit_loopback_test_fixture() -> None:
    policy = NetworkAccessPolicy(allow_loopback=True)

    policy.validate_url("http://127.0.0.1:8080/status")


def test_network_access_policy_allows_private_benchmark_address_when_local_access_is_enabled() -> None:
    policy = NetworkAccessPolicy(allow_local_network_access=True)

    policy.validate_url("http://198.18.1.94:3456/api/files")


@pytest.mark.parametrize(
    "url",
    ["http://169.254.169.254/latest/meta-data", "http://224.0.0.1/status"],
)
def test_network_access_policy_keeps_metadata_and_multicast_blocked_with_local_access(
    url: str,
) -> None:
    policy = NetworkAccessPolicy(allow_local_network_access=True)

    with pytest.raises(ValueError, match="network.access_denied"):
        policy.validate_url(url)


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest/meta-data", "http://10.0.0.1/"])
def test_network_access_policy_blocks_metadata_and_private_addresses(url: str) -> None:
    policy = NetworkAccessPolicy()

    with pytest.raises(ValueError, match="network.access_denied"):
        policy.validate_url(url)


def test_validated_network_backend_connects_to_validated_address_not_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingBackend:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        async def connect_tcp(self, host: str, port: int, **_: object) -> object:
            self.calls.append((host, port))
            return object()

        async def connect_unix_socket(self, path: str, **_: object) -> object:
            raise AssertionError(f"unexpected unix socket connection: {path}")

        async def sleep(self, _: float) -> None:
            return None

    def resolve_once(host: str, port: int | None, **_: object) -> list[tuple[object, ...]]:
        assert host == "rebind.example.test"
        assert port == 443
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", resolve_once)
    inner = RecordingBackend()
    backend = ValidatedNetworkBackend(NetworkAccessPolicy(), backend=inner)

    asyncio.run(backend.connect_tcp("rebind.example.test", 443, timeout=1.0))

    assert inner.calls == [("93.184.216.34", 443)]


def test_validated_network_backend_uses_request_pinned_address_without_dns_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingBackend:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        async def connect_tcp(self, host: str, port: int, **_: object) -> object:
            self.calls.append((host, port))
            return object()

        async def connect_unix_socket(self, path: str, **_: object) -> object:
            raise AssertionError(f"unexpected unix socket connection: {path}")

        async def sleep(self, _: float) -> None:
            return None

    def unexpected_dns(*_: object, **__: object) -> object:
        raise AssertionError("pinned connection must not resolve DNS again")

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_dns)
    inner = RecordingBackend()
    backend = ValidatedNetworkBackend(NetworkAccessPolicy(), backend=inner)
    backend.set_pinned_addresses(
        hostname="rebind.example.test",
        port=443,
        addresses=("93.184.216.34",),
    )

    asyncio.run(backend.connect_tcp("rebind.example.test", 443, timeout=1.0))

    assert inner.calls == [("93.184.216.34", 443)]


def test_pinned_dns_transport_keeps_hostname_origin_and_sni_while_using_pinned_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingPool:
        request: httpcore.Request | None = None

        async def handle_async_request(self, request: httpcore.Request) -> httpcore.Response:
            self.request = request

            async def empty_body():
                if False:
                    yield b""

            return httpcore.Response(status=204, headers=[], content=empty_body())

    def resolve_once(host: str, port: int | None, **_: object) -> list[tuple[object, ...]]:
        assert host == "rebind.example.test"
        assert port == 443
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", resolve_once)
    pool = RecordingPool()
    transport = object.__new__(PinnedDnsAsyncHTTPTransport)
    transport._access_policy = NetworkAccessPolicy()
    transport._pool = pool

    async def exercise() -> None:
        async with httpx.AsyncClient() as client:
            request = client.build_request("GET", "https://rebind.example.test/resource")
            response = await transport.handle_async_request(request)
            await response.aclose()

    asyncio.run(exercise())

    assert pool.request is not None
    assert pool.request.url.host == b"rebind.example.test"
    assert dict(pool.request.headers)[b"Host"] == b"rebind.example.test"
    assert pool.request.extensions["sni_hostname"] == "rebind.example.test"


def test_proxy_tunnel_uses_original_hostname_for_tls_sni_after_connecting_to_pinned_ip() -> None:
    request = httpcore.Request(
        method="GET",
        url="https://93.184.216.34/resource",
        extensions={"sni_hostname": "rebind.example.test"},
    )

    server_hostname = _resolve_tunnel_sni_hostname(
        request,
        remote_host=b"93.184.216.34",
    )

    assert server_hostname == b"rebind.example.test"


def test_pinned_proxy_transport_replaces_https_tunnel_connection_factory() -> None:
    transport = PinnedDnsAsyncHTTPTransport(
        access_policy=NetworkAccessPolicy(allow_loopback=True),
        proxy="http://127.0.0.1:8080",
    )

    connection = transport._pool.create_connection(
        httpcore.Origin(scheme=b"https", host=b"93.184.216.34", port=443)
    )

    assert isinstance(connection, _PinnedDnsAsyncTunnelHTTPConnection)
    assert connection._remote_origin.host == b"93.184.216.34"


def test_pinned_proxy_transport_uses_policy_approved_ip_for_proxy_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingPool:
        request: httpcore.Request | None = None

        async def handle_async_request(self, request: httpcore.Request) -> httpcore.Response:
            self.request = request

            async def empty_body():
                if False:
                    yield b""

            return httpcore.Response(status=204, headers=[], content=empty_body())

    monkeypatch.setattr(
        NetworkAccessPolicy,
        "resolve_connect_addresses",
        lambda _self, hostname, port: ("93.184.216.34",),
    )
    policy = NetworkAccessPolicy(allowed_hostnames=frozenset({"target.example.test"}))
    pool = RecordingPool()
    transport = object.__new__(PinnedDnsAsyncHTTPTransport)
    transport._access_policy = policy
    transport._pool = pool
    transport._uses_proxy = True

    async def exercise() -> None:
        async with httpx.AsyncClient() as client:
            request = client.build_request("GET", "https://target.example.test/resource")
            response = await transport.handle_async_request(request)
            await response.aclose()

    asyncio.run(exercise())

    assert pool.request is not None
    assert pool.request.url.host == b"93.184.216.34"
    assert dict(pool.request.headers)[b"Host"] == b"target.example.test"
    assert pool.request.extensions["sni_hostname"] == "target.example.test"
