from __future__ import annotations

import httpx

import weconduct.network_runtime.service as network_service_module
from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.service import NetworkRuntimeService


class _FakeConnectionHandle:
    def __init__(self, **kwargs) -> None:
        self.url = kwargs["url"]
        self.connection_id = kwargs.get("connection_id")
        self.sequence_allocator = kwargs["sequence_allocator"]
        self.activation_sink = kwargs.get("activation_sink")
        self.closed = False
        self.queue_status = {
            "depth": 0,
            "dropped_count": 0,
            "drop_events": [],
            "closed": False,
            "cancelled": False,
            "backpressure_policy": kwargs.get("backpressure_policy", "fail_stream"),
            "connection_id": self.connection_id,
            "connection_epoch": 1,
            "reconnect_count": 0,
            "connection_state": "connected",
        }

    def start(self, *, timeout_seconds=None):
        return {"status_code": 200, "headers": {}, "url": self.url}

    def emit(self, event_kind: str) -> dict[str, object]:
        activation = {
            "sequence_id": self.sequence_allocator.next(),
            "payload": {"event_kind": event_kind, "message": {"payload": event_kind}},
            "connection_id": self.connection_id,
            "connection_epoch": 1,
        }
        if callable(self.activation_sink):
            self.activation_sink(activation)
        return activation

    def close(self) -> None:
        self.closed = True
        self.queue_status = {**self.queue_status, "closed": True, "connection_state": "closed"}


def test_network_runtime_service_routes_multi_connection_activations_in_global_order(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(network_service_module, "SSEClientHandle", _FakeConnectionHandle)
    monkeypatch.setattr(network_service_module, "WebSocketClientHandle", _FakeConnectionHandle)
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    try:
        sse, _ = service.connect_sse(
            session_id="debug-activation",
            snapshot=network_service_module.NetworkContextSnapshot(context_id="context"),
            url="https://example.test/events",
            connection_id="sse",
        )
        websocket, _ = service.connect_websocket(
            session_id="debug-activation",
            snapshot=network_service_module.NetworkContextSnapshot(context_id="context"),
            url="wss://example.test/events",
            connection_id="websocket",
        )

        websocket_event = websocket.emit("websocket.message")
        sse_event = sse.emit("sse.message")

        assert websocket_event["sequence_id"] == 1
        assert sse_event["sequence_id"] == 2
        assert service.wait_connection_activation(
            session_id="debug-activation", handle=sse, timeout_seconds=1
        )["sequence_id"] == 2
        assert service.wait_connection_activation(
            session_id="debug-activation", handle=websocket, timeout_seconds=1
        )["sequence_id"] == 1
    finally:
        service.close()
