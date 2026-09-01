from __future__ import annotations

import pytest

from weconduct.application.operations import (
    HostOperationService,
    OperationCaller,
    OperationRegistryError,
)
from weconduct.application.operations.registry import OperationRegistry
from weconduct.api.external_v1.router import resolve_external_operation


_CALLER = OperationCaller(
    caller_id="test:oauth",
    permissions=frozenset({"operation.invoke"}),
)


class _OAuthHost:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def begin_oauth_authorization(self, **payload: object) -> dict[str, object]:
        self.calls.append(("authorization", payload))
        return {"flow_id": "flow-1", "status": "waiting_input"}

    def begin_oauth_device(self, **payload: object) -> dict[str, object]:
        self.calls.append(("device", payload))
        return {"flow_id": "flow-2", "status": "waiting_input"}

    def get_oauth_flow(self, *, flow_id: str) -> dict[str, object]:
        self.calls.append(("get", {"flow_id": flow_id}))
        return {"flow_id": flow_id, "status": "succeeded"}

    def submit_oauth_flow(self, *, flow_id: str, values: object) -> dict[str, object]:
        self.calls.append(("submit", {"flow_id": flow_id, "values": values}))
        return {"flow_id": flow_id, "status": "exchanging"}

    def cancel_oauth_flow(self, *, flow_id: str) -> dict[str, object]:
        self.calls.append(("cancel", {"flow_id": flow_id}))
        return {"flow_id": flow_id, "status": "cancelled"}


def test_oauth_operations_are_stable_and_delegate_to_shared_host_service() -> None:
    host = _OAuthHost()
    service = HostOperationService(service=host)

    started = service.invoke(
        "oauth.authorization.begin",
        {
            "authorization_url": "https://example.test/authorize",
            "token_url": "https://example.test/token",
            "client_id": "client",
            "redirect_uri": "http://127.0.0.1/callback",
            "scope_id": "flow-scope",
        },
        caller=_CALLER,
    )
    assert started["flow_id"] == "flow-1"
    assert host.calls[0][0] == "authorization"

    submitted = service.invoke(
        "oauth.flow.submit",
        {"flow_id": "flow-1", "values": {"code": "private-code"}},
        caller=_CALLER,
    )
    assert submitted["status"] == "exchanging"
    assert host.calls[-1][1]["values"] == {"code": "private-code"}


def test_oauth_external_routes_map_to_explicit_operations() -> None:
    assert resolve_external_operation(
        method="POST",
        request_path="/api/ext/v1/oauth/authorization",
        read_payload=lambda: {"client_id": "client"},
    ) == ("oauth.authorization.begin", {"client_id": "client"})
    assert resolve_external_operation(
        method="POST",
        request_path="/api/ext/v1/oauth/device",
        read_payload=lambda: {"client_id": "client"},
    ) == ("oauth.device.begin", {"client_id": "client"})
    assert resolve_external_operation(
        method="GET",
        request_path="/api/ext/v1/oauth/flow-1",
    ) == ("oauth.flow.get", {"flow_id": "flow-1"})
    for reserved_path in ("authorization", "device"):
        with pytest.raises(OperationRegistryError) as error_info:
            resolve_external_operation(
                method="GET",
                request_path=f"/api/ext/v1/oauth/{reserved_path}",
            )
        assert error_info.value.error_code == "operation.not_found"
    assert resolve_external_operation(
        method="POST",
        request_path="/api/ext/v1/oauth/flow-1/submit",
        read_payload=lambda: {"values": {"code": "private-code"}},
    ) == ("oauth.flow.submit", {"flow_id": "flow-1", "values": {"code": "private-code"}})
    assert resolve_external_operation(
        method="POST",
        request_path="/api/ext/v1/oauth/flow-1/cancel",
    ) == ("oauth.flow.cancel", {"flow_id": "flow-1"})


def test_oauth_operation_registry_contains_no_plugin_exposure() -> None:
    registry = OperationRegistry.build_stable_public()
    for operation_id in (
        "oauth.authorization.begin",
        "oauth.device.begin",
        "oauth.flow.get",
        "oauth.flow.submit",
        "oauth.flow.cancel",
    ):
        assert registry.describe(operation_id).exposure.value == "stable_public"
