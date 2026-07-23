from __future__ import annotations

import asyncio

import httpx

from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation
from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.service import NetworkRuntimeService


def test_network_runtime_service_executes_on_its_owned_loop_and_closes_cleanly(tmp_path) -> None:
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(204, request=request)
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    operation = NetworkOperation(
        operation_id="request-1",
        session_id="session-1",
        method="GET",
        url="https://example.test/ok",
    )

    result = service.submit(
        operation,
        NetworkContextSnapshot(context_id="context-1"),
    ).result(timeout=1)
    service.close()

    assert result.status_code == 204
    assert service.is_closed is True


def test_network_runtime_service_cancels_active_session_requests(tmp_path) -> None:
    async def slow_response(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(204, request=request)

    service = NetworkRuntimeService(
        transport=httpx.MockTransport(slow_response),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    future = service.submit(
        NetworkOperation(
            operation_id="request-cancel",
            session_id="session-cancel",
            method="GET",
            url="https://example.test/slow",
        ),
        NetworkContextSnapshot(context_id="context-1"),
    )
    service.cancel_session("session-cancel")
    result = future.result(timeout=1)
    service.close()

    assert result.status == "failed"
    assert result.transport_error == "network.cancelled"
