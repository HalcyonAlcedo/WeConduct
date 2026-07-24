from __future__ import annotations

import asyncio
from pathlib import Path
from time import perf_counter
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
        started_at = perf_counter()
        try:
            headers = {**snapshot.headers, **operation.headers}
            content = operation.content
            if operation.upload_file_path is not None:
                content = _iter_upload_file_chunks(operation.upload_file_path)
            request_url = operation.url
            for _ in range(10):
                self._access_policy.validate_url(request_url)
                async with self._client.stream(
                    operation.method,
                    request_url,
                    headers=headers,
                    content=content,
                    timeout=operation.timeout_seconds,
                ) as response:
                    redirect_target = response.headers.get("location")
                    if response.status_code not in {301, 302, 303, 307, 308} or not redirect_target:
                        store = self._stores.setdefault(
                            operation.session_id,
                            ResponseBodyStore(
                                session_id=operation.session_id,
                                root_directory=self._response_root_directory,
                            ),
                        )
                        body_ref = await store.create_from_async_chunks(
                            response.aiter_bytes(),
                            content_type=response.headers.get("content-type"),
                            force_file=operation.response_storage == "file",
                        )
                        break
                    request_url = urljoin(request_url, redirect_target)
            else:
                return NetworkResult(
                    status="failed",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    transport_error="network.too_many_redirects",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
        except asyncio.CancelledError:
            return NetworkResult(
                status="failed",
                operation_id=operation.operation_id,
                session_id=operation.session_id,
                transport_error="network.cancelled",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return NetworkResult(
                status="failed",
                operation_id=operation.operation_id,
                session_id=operation.session_id,
                transport_error=str(exc),
                duration_ms=(perf_counter() - started_at) * 1000,
            )
        return NetworkResult(
            status="succeeded",
            operation_id=operation.operation_id,
            session_id=operation.session_id,
            status_code=response.status_code,
            headers=dict(response.headers),
            body_ref=body_ref,
            final_url=str(response.url),
            duration_ms=(perf_counter() - started_at) * 1000,
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


async def _iter_upload_file_chunks(path: Path, *, chunk_size: int = 64 * 1024):
    with Path(path).open("rb") as handle:
        while chunk := await asyncio.to_thread(handle.read, chunk_size):
            yield chunk
