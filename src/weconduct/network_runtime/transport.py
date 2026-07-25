from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Iterable
from typing import Any

import httpcore
import httpx
from httpcore._backends.auto import AutoBackend
from httpx._transports.default import AsyncResponseStream, map_httpcore_exceptions
from httpx._types import AsyncByteStream

from .access_policy import NetworkAccessPolicy, ResolvedNetworkTarget


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

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
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


class PinnedDnsAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport that pins each target connection to policy-approved DNS output."""

    def __init__(self, *, access_policy: NetworkAccessPolicy, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._access_policy = access_policy
        self._pool._network_backend = ValidatedNetworkBackend(access_policy)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert isinstance(request.stream, AsyncByteStream)
        target_host = request.url.host
        target_port = request.url.port
        connect_port = target_port or (443 if request.url.scheme == "https" else 80)
        if isinstance(self._pool, httpcore.AsyncHTTPProxy):
            # The proxy pool connects through its own proxy origin. Resolving the target
            # here both defeats proxy-side DNS and rejects deliberately non-resolvable names.
            connect_host = request.url.raw_host
        else:
            resolved_target = request.extensions.get("weconduct.resolved_network_target")
            if (
                isinstance(resolved_target, ResolvedNetworkTarget)
                and resolved_target.hostname == target_host.lower()
                and resolved_target.port == connect_port
            ):
                addresses = resolved_target.addresses
            else:
                addresses = self._access_policy.resolve_connect_addresses(target_host, connect_port)
            connect_host = addresses[0].encode("ascii")
        extensions = {**request.extensions, "sni_hostname": target_host}
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=connect_host,
                port=target_port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=extensions,
        )
        with map_httpcore_exceptions():
            core_response = await self._pool.handle_async_request(core_request)
        assert isinstance(core_response.stream, AsyncIterable)
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=AsyncResponseStream(core_response.stream),
            extensions=core_response.extensions,
        )
