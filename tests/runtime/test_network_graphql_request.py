from __future__ import annotations

from concurrent.futures import Future
import json

from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from weconduct.network_runtime.resources import ResponseBodyRef
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_network_graphql_request_returns_data_errors_and_extensions() -> None:
    class StubNetworkRuntimeService:
        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            future: Future[NetworkResult] = Future()
            payload = json.dumps(
                {"data": {"health": True}, "errors": [{"message": "partial"}], "extensions": {"trace": "x"}}
            ).encode("utf-8")
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                    body_ref=ResponseBodyRef(
                        session_id=operation.session_id,
                        storage_kind="memory",
                        size_bytes=len(payload),
                        content_type="application/json",
                        _payload=payload,
                    ),
                )
            )
            return future

    node = {
        "node_id": "graphql-1",
        "node_kind": "network.graphql_request",
        "node_config": {
            "endpoint": "https://example.test/graphql",
            "query": "query Health { health }",
            "variables": {},
        },
    }

    output = RuntimeExecutorRegistry(network_runtime_service=StubNetworkRuntimeService()).execute(
        "network.graphql_request", node, RuntimeContext()
    )

    assert output["status"] == "succeeded"
    assert output["data"] == {"health": True}
    assert output["errors"] == [{"message": "partial"}]
    assert output["extensions"] == {"trace": "x"}


def test_network_graphql_subscription_uses_websocket_transport(monkeypatch) -> None:
    import weconduct.runtime.engine as engine_module

    class FakeWebSocketClientHandle:
        instances: list["FakeWebSocketClientHandle"] = []

        def __init__(self, *, url, headers=None, proxy=None, timeout_seconds=30.0, subprotocols=None):
            self.url = url
            self.headers = headers or {}
            self.proxy = proxy
            self.timeout_seconds = timeout_seconds
            self.subprotocols = subprotocols or []
            self.sent: list[object] = []
            self.closed = False
            self.received = [
                '{"id":"subscription-1","type":"next","payload":{"data":{"updates":[{"id":"1"}]}}}',
            ]
            self.__class__.instances.append(self)

        def start(self, *, timeout_seconds=None):
            return {"status": "connected", "url": self.url}

        def send(self, value):
            self.sent.append(value)

        def receive(self, *, timeout_seconds=None):
            return self.received.pop(0)

        def close(self):
            self.closed = True

    class StubNetworkRuntimeService:
        def connect_websocket(self, **kwargs):
            handle = FakeWebSocketClientHandle(
                url=kwargs["url"],
                headers=kwargs.get("headers"),
                timeout_seconds=kwargs.get("timeout_seconds", 30.0),
                subprotocols=kwargs.get("subprotocols"),
            )
            return handle, handle.start(timeout_seconds=kwargs.get("timeout_seconds"))

    monkeypatch.setattr(engine_module, "WebSocketClientHandle", FakeWebSocketClientHandle)
    registry = RuntimeExecutorRegistry(network_runtime_service=StubNetworkRuntimeService())
    context = RuntimeContext()
    node = {
        "node_id": "subscription-node",
        "node_kind": "network.graphql_request",
        "node_config": {
            "action": "connect",
            "connection_id": "subscription-1",
            "endpoint": "https://example.test/graphql",
            "query": "subscription Watch { updates { id } }",
            "operation_name": "Watch",
        },
    }

    connected = registry.execute("network.graphql_request", node, context)
    received = registry.execute(
        "network.graphql_request",
        {
            **node,
            "node_config": {
                "action": "receive",
                "connection_id": "subscription-1",
            },
        },
        context,
    )

    assert connected["status"] == "succeeded"
    assert received["data"] == {"updates": [{"id": "1"}]}
    assert json.loads(FakeWebSocketClientHandle.instances[0].sent[0])["type"] == "connection_init"
