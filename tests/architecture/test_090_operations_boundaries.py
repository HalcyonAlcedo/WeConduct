from __future__ import annotations

import inspect

from weconduct.api.server import WeConductApiHandler, WeConductApiServer


def test_090_operations_and_external_v1_are_explicit_packages() -> None:
    from weconduct.application.operations import HostOperationService, OperationRegistry
    from weconduct.api.external_v1.router import ExternalV1Router

    assert HostOperationService.__module__.startswith("weconduct.application.operations")
    assert OperationRegistry.__module__.startswith("weconduct.application.operations")
    assert ExternalV1Router.__module__ == "weconduct.api.external_v1.router"


def test_090_external_v1_handler_entry_is_thin_router_delegation() -> None:
    source = inspect.getsource(WeConductApiHandler._handle_external_api)

    assert "ExternalV1Router" in source
    assert "_resolve_external_operation" not in source


def test_090_api_server_does_not_keep_a_second_external_idempotency_cache() -> None:
    source = inspect.getsource(WeConductApiServer)

    assert "begin_external_idempotency" not in source
    assert "complete_external_idempotency" not in source
    assert "external_api_idempotency_store" in source
