from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Iterable
import logging
from threading import RLock
from typing import Any

import httpcore
import httpx
from httpcore._async.http11 import AsyncHTTP11Connection
from httpcore._async.http2 import AsyncHTTP2Connection
from httpcore._async.http_proxy import AsyncTunnelHTTPConnection
from httpcore._backends.auto import AutoBackend
from httpcore._backends.sync import SyncBackend
from httpcore._exceptions import ProxyError
from httpcore._ssl import default_ssl_context
from httpcore._sync.http11 import HTTP11Connection
from httpcore._sync.http2 import HTTP2Connection
from httpcore._sync.http_proxy import TunnelHTTPConnection
from httpcore._trace import Trace
from httpx._transports.default import AsyncResponseStream, ResponseStream, map_httpcore_exceptions
from httpx._types import AsyncByteStream, SyncByteStream

from .access_policy import NetworkAccessPolicy, ResolvedNetworkTarget


_PROXY_LOGGER = logging.getLogger("httpcore.proxy")


def _resolve_tunnel_sni_hostname(request: httpcore.Request, *, remote_host: bytes) -> bytes:
    configured_hostname = request.extensions.get("sni_hostname")
    if isinstance(configured_hostname, str):
        try:
            return configured_hostname.encode("ascii")
        except UnicodeEncodeError:
            return remote_host
    if isinstance(configured_hostname, bytes) and configured_hostname:
        return configured_hostname
    return remote_host


class _PinnedDnsAsyncTunnelHTTPConnection(AsyncTunnelHTTPConnection):
    """代理以已批准 IP CONNECT，同时对 TLS 保留请求原始 SNI。"""

    async def handle_async_request(self, request: httpcore.Request) -> httpcore.Response:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("connect", None)

        async with self._connect_lock:
            if not self._connected:
                target = b"%b:%d" % (self._remote_origin.host, self._remote_origin.port)
                connect_url = httpcore.URL(
                    scheme=self._proxy_origin.scheme,
                    host=self._proxy_origin.host,
                    port=self._proxy_origin.port,
                    target=target,
                )
                connect_headers = [
                    (b"Host", target),
                    (b"Accept", b"*/*"),
                    *self._proxy_headers,
                ]
                connect_request = httpcore.Request(
                    method=b"CONNECT",
                    url=connect_url,
                    headers=connect_headers,
                    extensions=request.extensions,
                )
                connect_response = await self._connection.handle_async_request(connect_request)
                if connect_response.status < 200 or connect_response.status > 299:
                    reason_bytes = connect_response.extensions.get("reason_phrase", b"")
                    reason_str = reason_bytes.decode("ascii", errors="ignore")
                    await self._connection.aclose()
                    raise ProxyError(f"{connect_response.status} {reason_str}")

                stream = connect_response.extensions["network_stream"]
                ssl_context = self._ssl_context or default_ssl_context()
                ssl_context.set_alpn_protocols(["http/1.1", "h2"] if self._http2 else ["http/1.1"])
                tls_kwargs = {
                    "ssl_context": ssl_context,
                    "server_hostname": _resolve_tunnel_sni_hostname(
                        request,
                        remote_host=self._remote_origin.host,
                    ).decode("ascii"),
                    "timeout": timeout,
                }
                async with Trace("start_tls", _PROXY_LOGGER, request, tls_kwargs) as trace:
                    stream = await stream.start_tls(**tls_kwargs)
                    trace.return_value = stream
                ssl_object = stream.get_extra_info("ssl_object")
                http2_negotiated = (
                    ssl_object is not None and ssl_object.selected_alpn_protocol() == "h2"
                )
                if http2_negotiated or (self._http2 and not self._http1):
                    self._connection = AsyncHTTP2Connection(
                        origin=self._remote_origin,
                        stream=stream,
                        keepalive_expiry=self._keepalive_expiry,
                    )
                else:
                    self._connection = AsyncHTTP11Connection(
                        origin=self._remote_origin,
                        stream=stream,
                        keepalive_expiry=self._keepalive_expiry,
                    )
                self._connected = True
        return await self._connection.handle_async_request(request)


class _PinnedDnsTunnelHTTPConnection(TunnelHTTPConnection):
    """同步版本的代理 IP CONNECT 与原始 TLS SNI 连接。"""

    def handle_request(self, request: httpcore.Request) -> httpcore.Response:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("connect", None)

        with self._connect_lock:
            if not self._connected:
                target = b"%b:%d" % (self._remote_origin.host, self._remote_origin.port)
                connect_url = httpcore.URL(
                    scheme=self._proxy_origin.scheme,
                    host=self._proxy_origin.host,
                    port=self._proxy_origin.port,
                    target=target,
                )
                connect_headers = [
                    (b"Host", target),
                    (b"Accept", b"*/*"),
                    *self._proxy_headers,
                ]
                connect_request = httpcore.Request(
                    method=b"CONNECT",
                    url=connect_url,
                    headers=connect_headers,
                    extensions=request.extensions,
                )
                connect_response = self._connection.handle_request(connect_request)
                if connect_response.status < 200 or connect_response.status > 299:
                    reason_bytes = connect_response.extensions.get("reason_phrase", b"")
                    reason_str = reason_bytes.decode("ascii", errors="ignore")
                    self._connection.close()
                    raise ProxyError(f"{connect_response.status} {reason_str}")

                stream = connect_response.extensions["network_stream"]
                ssl_context = self._ssl_context or default_ssl_context()
                ssl_context.set_alpn_protocols(["http/1.1", "h2"] if self._http2 else ["http/1.1"])
                tls_kwargs = {
                    "ssl_context": ssl_context,
                    "server_hostname": _resolve_tunnel_sni_hostname(
                        request,
                        remote_host=self._remote_origin.host,
                    ).decode("ascii"),
                    "timeout": timeout,
                }
                with Trace("start_tls", _PROXY_LOGGER, request, tls_kwargs) as trace:
                    stream = stream.start_tls(**tls_kwargs)
                    trace.return_value = stream
                ssl_object = stream.get_extra_info("ssl_object")
                http2_negotiated = (
                    ssl_object is not None and ssl_object.selected_alpn_protocol() == "h2"
                )
                if http2_negotiated or (self._http2 and not self._http1):
                    self._connection = HTTP2Connection(
                        origin=self._remote_origin,
                        stream=stream,
                        keepalive_expiry=self._keepalive_expiry,
                    )
                else:
                    self._connection = HTTP11Connection(
                        origin=self._remote_origin,
                        stream=stream,
                        keepalive_expiry=self._keepalive_expiry,
                    )
                self._connected = True
        return self._connection.handle_request(request)


def _install_async_pinned_proxy_tunnel(pool: httpcore.AsyncHTTPProxy) -> None:
    default_create_connection = pool.create_connection

    def create_connection(origin: httpcore.Origin) -> httpcore.AsyncConnectionInterface:
        if origin.scheme == b"http":
            return default_create_connection(origin)
        return _PinnedDnsAsyncTunnelHTTPConnection(
            proxy_origin=pool._proxy_url.origin,
            proxy_headers=pool._proxy_headers,
            remote_origin=origin,
            ssl_context=pool._ssl_context,
            proxy_ssl_context=pool._proxy_ssl_context,
            keepalive_expiry=pool._keepalive_expiry,
            http1=pool._http1,
            http2=pool._http2,
            network_backend=pool._network_backend,
        )

    pool.create_connection = create_connection  # type: ignore[method-assign]


def _install_sync_pinned_proxy_tunnel(pool: httpcore.HTTPProxy) -> None:
    default_create_connection = pool.create_connection

    def create_connection(origin: httpcore.Origin) -> httpcore.ConnectionInterface:
        if origin.scheme == b"http":
            return default_create_connection(origin)
        return _PinnedDnsTunnelHTTPConnection(
            proxy_origin=pool._proxy_url.origin,
            proxy_headers=pool._proxy_headers,
            remote_origin=origin,
            ssl_context=pool._ssl_context,
            proxy_ssl_context=pool._proxy_ssl_context,
            keepalive_expiry=pool._keepalive_expiry,
            http1=pool._http1,
            http2=pool._http2,
            network_backend=pool._network_backend,
        )

    pool.create_connection = create_connection  # type: ignore[method-assign]


class ValidatedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Connects to resolved IP addresses instead of triggering a second DNS lookup."""

    def __init__(
        self,
        access_policy: NetworkAccessPolicy,
        *,
        backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._access_policy = access_policy
        self._backend = backend or AutoBackend()
        self._pinned_addresses: dict[tuple[str, int], tuple[tuple[str, ...], int]] = {}
        self._pinned_addresses_lock = RLock()

    def set_pinned_addresses(
        self,
        *,
        hostname: str,
        port: int,
        addresses: Iterable[str],
    ) -> None:
        with self._pinned_addresses_lock:
            key = (hostname.lower(), port)
            _, active_request_count = self._pinned_addresses.get(key, ((), 0))
            self._pinned_addresses[key] = (tuple(addresses), active_request_count + 1)

    def clear_pinned_addresses(self, *, hostname: str, port: int) -> None:
        with self._pinned_addresses_lock:
            key = (hostname.lower(), port)
            pinned = self._pinned_addresses.get(key)
            if pinned is None or pinned[1] <= 1:
                self._pinned_addresses.pop(key, None)
            else:
                self._pinned_addresses[key] = (pinned[0], pinned[1] - 1)

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        with self._pinned_addresses_lock:
            pinned = self._pinned_addresses.get((host.lower(), port))
            addresses = pinned[0] if pinned is not None else None
        if not addresses:
            addresses = self._access_policy.resolve_connect_addresses(host, port)
        last_error: OSError | httpcore.NetworkError | None = None
        for address in addresses:
            try:
                return await self._backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except asyncio.CancelledError:
                raise
            except (OSError, httpcore.NetworkError) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._backend.connect_unix_socket(
            path,
            timeout=timeout,
            socket_options=socket_options,
        )

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class ValidatedSyncNetworkBackend(httpcore.NetworkBackend):
    """同步 OAuth 路径使用的 DNS 固定连接后端。"""

    def __init__(
        self,
        access_policy: NetworkAccessPolicy,
        *,
        backend: httpcore.NetworkBackend | None = None,
    ) -> None:
        self._access_policy = access_policy
        self._backend = backend or SyncBackend()
        self._pinned_addresses: dict[tuple[str, int], tuple[tuple[str, ...], int]] = {}
        self._pinned_addresses_lock = RLock()

    def set_pinned_addresses(
        self,
        *,
        hostname: str,
        port: int,
        addresses: Iterable[str],
    ) -> None:
        with self._pinned_addresses_lock:
            key = (hostname.lower(), port)
            _, active_request_count = self._pinned_addresses.get(key, ((), 0))
            self._pinned_addresses[key] = (tuple(addresses), active_request_count + 1)

    def clear_pinned_addresses(self, *, hostname: str, port: int) -> None:
        with self._pinned_addresses_lock:
            key = (hostname.lower(), port)
            pinned = self._pinned_addresses.get(key)
            if pinned is None or pinned[1] <= 1:
                self._pinned_addresses.pop(key, None)
            else:
                self._pinned_addresses[key] = (pinned[0], pinned[1] - 1)

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        with self._pinned_addresses_lock:
            pinned = self._pinned_addresses.get((host.lower(), port))
            addresses = pinned[0] if pinned is not None else None
        if not addresses:
            addresses = self._access_policy.resolve_connect_addresses(host, port)
        last_error: OSError | httpcore.NetworkError | None = None
        for address in addresses:
            try:
                return self._backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (OSError, httpcore.NetworkError) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        return self._backend.connect_unix_socket(
            path,
            timeout=timeout,
            socket_options=socket_options,
        )

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


class PinnedDnsAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport that pins each target connection to policy-approved DNS output."""

    def __init__(self, *, access_policy: NetworkAccessPolicy, **kwargs: Any) -> None:
        self._uses_proxy = kwargs.get("proxy") is not None
        if self._uses_proxy:
            # 代理以批准 IP 作为目标时，不能复用不同域名的 TLS 连接。
            kwargs["http2"] = False
            kwargs["limits"] = httpx.Limits(max_keepalive_connections=0)
        super().__init__(**kwargs)
        self._access_policy = access_policy
        self._validated_network_backend = ValidatedNetworkBackend(access_policy)
        self._pool._network_backend = self._validated_network_backend
        if self._uses_proxy and isinstance(self._pool, httpcore.AsyncHTTPProxy):
            _install_async_pinned_proxy_tunnel(self._pool)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert isinstance(request.stream, AsyncByteStream)
        target_host = request.url.host
        target_port = request.url.port
        connect_port = target_port or (443 if request.url.scheme == "https" else 80)
        uses_proxy = getattr(self, "_uses_proxy", False)
        addresses: tuple[str, ...] = ()
        if not uses_proxy:
            resolved_target = request.extensions.get("weconduct.resolved_network_target")
            if (
                isinstance(resolved_target, ResolvedNetworkTarget)
                and resolved_target.hostname == target_host.lower()
                and resolved_target.port == connect_port
            ):
                addresses = resolved_target.addresses
            else:
                addresses = self._access_policy.resolve_connect_addresses(target_host, connect_port)
        backend = getattr(self, "_validated_network_backend", None)
        if not uses_proxy and isinstance(backend, ValidatedNetworkBackend):
            backend.set_pinned_addresses(
                hostname=target_host,
                port=connect_port,
                addresses=addresses,
            )
        extensions = {**request.extensions, "sni_hostname": target_host}
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=target_port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=extensions,
        )
        try:
            with map_httpcore_exceptions():
                core_response = await self._pool.handle_async_request(core_request)
        finally:
            if not uses_proxy and isinstance(backend, ValidatedNetworkBackend):
                backend.clear_pinned_addresses(hostname=target_host, port=connect_port)
        assert isinstance(core_response.stream, AsyncIterable)
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=AsyncResponseStream(core_response.stream),
            extensions=core_response.extensions,
        )


class PinnedDnsHTTPTransport(httpx.HTTPTransport):
    """同步 HTTPX transport，供 OAuth 等同步调用绑定已校验 DNS 结果。"""

    def __init__(self, *, access_policy: NetworkAccessPolicy, **kwargs: Any) -> None:
        self._uses_proxy = kwargs.get("proxy") is not None
        if self._uses_proxy:
            # 代理以批准 IP 作为目标时，不能复用不同域名的 TLS 连接。
            kwargs["http2"] = False
            kwargs["limits"] = httpx.Limits(max_keepalive_connections=0)
        super().__init__(**kwargs)
        self._access_policy = access_policy
        self._validated_network_backend = ValidatedSyncNetworkBackend(access_policy)
        self._pool._network_backend = self._validated_network_backend
        if self._uses_proxy and isinstance(self._pool, httpcore.HTTPProxy):
            _install_sync_pinned_proxy_tunnel(self._pool)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        assert isinstance(request.stream, SyncByteStream)
        target_host = request.url.host
        target_port = request.url.port
        connect_port = target_port or (443 if request.url.scheme == "https" else 80)
        uses_proxy = getattr(self, "_uses_proxy", False)
        addresses: tuple[str, ...] = ()
        if not uses_proxy:
            resolved_target = request.extensions.get("weconduct.resolved_network_target")
            if (
                isinstance(resolved_target, ResolvedNetworkTarget)
                and resolved_target.hostname == target_host.lower()
                and resolved_target.port == connect_port
            ):
                addresses = resolved_target.addresses
            else:
                addresses = self._access_policy.resolve_connect_addresses(target_host, connect_port)
        backend = getattr(self, "_validated_network_backend", None)
        if not uses_proxy and isinstance(backend, ValidatedSyncNetworkBackend):
            backend.set_pinned_addresses(
                hostname=target_host,
                port=connect_port,
                addresses=addresses,
            )
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=target_port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions={**request.extensions, "sni_hostname": target_host},
        )
        try:
            with map_httpcore_exceptions():
                core_response = self._pool.handle_request(core_request)
        finally:
            if not uses_proxy and isinstance(backend, ValidatedSyncNetworkBackend):
                backend.clear_pinned_addresses(hostname=target_host, port=connect_port)
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=ResponseStream(core_response.stream),
            extensions=core_response.extensions,
        )
