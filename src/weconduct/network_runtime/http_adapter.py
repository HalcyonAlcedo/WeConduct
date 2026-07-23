from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urljoin

import httpx

from .access_policy import NetworkAccessPolicy
from .models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from .resources import ResponseBodyStore


class HttpxAdapter:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        response_root_directory: Path,
        access_policy: NetworkAccessPolicy | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
        )
        self._owns_client = client is None
        self._response_root_directory = Path(response_root_directory)
        self._access_policy = access_policy or NetworkAccessPolicy()
        self._stores: dict[str, ResponseBodyStore] = {}

    def execute(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
    ) -> NetworkResult:
        return asyncio.run(self.execute_async(operation, snapshot))

    async def execute_async(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
    ) -> NetworkResult:
        try:
            headers = {**snapshot.headers, **operation.headers}
            request_url = operation.url
            for _ in range(10):
                self._access_policy.validate_url(request_url)
                response = await self._client.request(
                    operation.method,
                    request_url,
                    headers=headers,
                    content=operation.content,
                    timeout=operation.timeout_seconds,
                )
                redirect_target = response.headers.get("location")
                if response.status_code not in {301, 302, 303, 307, 308} or not redirect_target:
                    break
                request_url = urljoin(request_url, redirect_target)
            else:
                return NetworkResult(
                    status="failed",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    transport_error="network.too_many_redirects",
                )
        except asyncio.CancelledError:
            return NetworkResult(
                status="failed",
                operation_id=operation.operation_id,
                session_id=operation.session_id,
                transport_error="network.cancelled",
            )
        except (httpx.HTTPError, ValueError) as exc:
            return NetworkResult(
                status="failed",
                operation_id=operation.operation_id,
                session_id=operation.session_id,
                transport_error=str(exc),
            )
        store = self._stores.setdefault(
            operation.session_id,
            ResponseBodyStore(
                session_id=operation.session_id,
                root_directory=self._response_root_directory,
            ),
        )
        return NetworkResult(
            status="succeeded",
            operation_id=operation.operation_id,
            session_id=operation.session_id,
            status_code=response.status_code,
            headers=dict(response.headers),
            body_ref=store.create(
                response.content,
                content_type=response.headers.get("content-type"),
            ),
            final_url=str(response.url),
        )

    def close_session(self, session_id: str) -> None:
        store = self._stores.pop(session_id, None)
        if store is not None:
            store.close()

    def close(self) -> None:
        for session_id in list(self._stores):
            self.close_session(session_id)

    async def aclose(self) -> None:
        self.close()
        if self._owns_client:
            await self._client.aclose()
