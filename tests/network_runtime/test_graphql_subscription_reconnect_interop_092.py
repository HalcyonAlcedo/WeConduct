from __future__ import annotations

import asyncio
import json
from json import loads
from threading import Event, Thread
from time import monotonic

import websockets

from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.service import NetworkRuntimeService
from weconduct.network_runtime.trace import NetworkTraceRecorder
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_graphql_subscription_reconnects_against_real_local_server(tmp_path) -> None:
    ready = Event()
    stop = Event()
    server_info: dict[str, object] = {"connection_count": 0, "frames": []}

    async def handler(socket) -> None:
        server_info["connection_count"] = int(server_info["connection_count"]) + 1
        connection_number = int(server_info["connection_count"])
        frames = server_info["frames"]
        assert isinstance(frames, list)
        connection_frames: list[dict[str, object]] = []
        frames.append(connection_frames)

        init_frame = loads(await socket.recv())
        connection_frames.append(init_frame)
        await socket.send('{"type":"connection_ack"}')
        ack_frame = {"type": "connection_ack"}
        connection_frames.append(ack_frame)

        subscribe_frame = loads(await socket.recv())
        connection_frames.append(subscribe_frame)
        await socket.send(
            json.dumps(
                {
                    "id": subscribe_frame.get("id"),
                    "type": "next",
                    "payload": {"data": {"tick": connection_number}},
                }
            )
        )
        if connection_number == 1:
            await asyncio.sleep(0.05)
            await socket.close(code=1011, reason="fixture reconnect")
            return

        while not stop.is_set():
            await asyncio.sleep(0.01)
        await socket.close()

    async def run_server() -> None:
        server = await websockets.serve(handler, "127.0.0.1", 0)
        server_info["server"] = server
        server_info["port"] = server.sockets[0].getsockname()[1]
        ready.set()
        while not stop.is_set():
            await asyncio.sleep(0.01)
        server.close()
        await server.wait_closed()

    def server_thread() -> None:
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_server())
        finally:
            loop.close()

    thread = Thread(target=server_thread, daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    port = int(server_info["port"])

    recorder = NetworkTraceRecorder()
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allow_loopback=True),
        trace_recorder=recorder,
    )
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    )
    node = {
        "node_id": "graphql-reconnect-real",
        "node_kind": "network.graphql_subscription",
        "node_config": {
            "action": "connect",
            "connection_id": "graphql-reconnect-real",
            "endpoint": f"ws://127.0.0.1:{port}/api/network/graphql-ws",
            "query": "subscription Tick { tick }",
            "timeout_seconds": 2,
            "max_reconnect_attempts": 1,
            "reconnect_delay_seconds": 0,
            "reconnect_max_delay_seconds": 0,
        },
    }
    try:
        connected = registry.execute("network.graphql_subscription", node, context)
        first = registry.execute(
            "network.graphql_subscription",
            {
                **node,
                "node_id": "graphql-reconnect-real-first",
                "node_config": {
                    "action": "next_event",
                    "connection_id": "graphql-reconnect-real",
                    "timeout_seconds": 2,
                },
            },
            context,
        )
        second = registry.execute(
            "network.graphql_subscription",
            {
                **node,
                "node_id": "graphql-reconnect-real-second",
                "node_config": {
                    "action": "next_event",
                    "connection_id": "graphql-reconnect-real",
                    "timeout_seconds": 2,
                },
            },
            context,
        )
    finally:
        context.close()
        service.close()
        stop.set()
        thread.join(timeout=2)

    assert connected["status"] == "succeeded", connected
    assert first["status"] == "succeeded", first
    assert first["data"] == {"tick": 1}, first
    assert second["status"] == "succeeded", second
    assert second["data"] == {"tick": 2}, second
    assert second["connection_epoch"] == 2, second
    assert int(server_info["connection_count"]) == 2
    frames = server_info["frames"]
    assert isinstance(frames, list)
    assert [[frame["type"] for frame in connection] for connection in frames] == [
        ["connection_init", "connection_ack", "subscribe"],
        ["connection_init", "connection_ack", "subscribe"],
    ]
    detail: dict[str, object] = {}
    next_messages: list[dict[str, object]] = []
    deadline = monotonic() + 1
    while monotonic() < deadline:
        traces = recorder.list_traces(debug_session_id="runtime-context")
        operation = next((item for item in traces if "method" in item), None)
        if operation is not None:
            candidate_detail = recorder.get_trace(operation["trace_id"])
            candidate_messages = []
            for item in candidate_detail["messages"]:
                if item["event_kind"] != "websocket.message":
                    continue
                payload = item["payload"]
                if isinstance(payload, dict):
                    is_next = payload.get("type") == "next"
                elif isinstance(payload, str):
                    is_next = loads(payload).get("type") == "next"
                else:
                    is_next = False
                if is_next:
                    candidate_messages.append(item)
            detail = candidate_detail
            next_messages = candidate_messages
            if len(next_messages) >= 2:
                break
        Event().wait(0.01)
    assert [item["connection_epoch"] for item in next_messages] == [1, 2], detail


def test_graphql_subscription_reconnects_multiple_epochs_then_unsubscribes_cleanly(tmp_path) -> None:
    """多次断线后取消订阅必须关闭最新 socket 并释放会话资源。"""
    ready = Event()
    stop = Event()
    complete_received = Event()
    server_info: dict[str, object] = {"connection_count": 0, "frames": [], "errors": []}

    async def handler(socket) -> None:
        server_info["connection_count"] = int(server_info["connection_count"]) + 1
        connection_number = int(server_info["connection_count"])
        frames = server_info["frames"]
        errors = server_info["errors"]
        assert isinstance(frames, list)
        assert isinstance(errors, list)
        connection_frames: list[dict[str, object]] = []
        frames.append(connection_frames)
        try:
            init_frame = loads(await asyncio.wait_for(socket.recv(), timeout=2))
            connection_frames.append(init_frame)
            await socket.send('{"type":"connection_ack"}')
            connection_frames.append({"type": "connection_ack"})

            subscribe_frame = loads(await asyncio.wait_for(socket.recv(), timeout=2))
            connection_frames.append(subscribe_frame)
            await socket.send(
                json.dumps(
                    {
                        "id": subscribe_frame.get("id"),
                        "type": "next",
                        "payload": {"data": {"tick": connection_number}},
                    }
                )
            )
            if connection_number <= 2:
                await asyncio.sleep(0.03)
                await socket.close(code=1011, reason="fixture repeated reconnect")
                return

            while not stop.is_set():
                try:
                    raw_frame = await asyncio.wait_for(socket.recv(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                frame = loads(raw_frame)
                connection_frames.append(frame)
                if frame.get("type") in {"complete", "stop"}:
                    complete_received.set()
                    await socket.close()
                    return
        except BaseException as exc:  # pragma: no cover - included in assertion output
            errors.append(str(exc))

    async def run_server() -> None:
        server = await websockets.serve(handler, "127.0.0.1", 0)
        server_info["server"] = server
        server_info["port"] = server.sockets[0].getsockname()[1]
        ready.set()
        while not stop.is_set():
            await asyncio.sleep(0.01)
        server.close()
        await server.wait_closed()

    def server_thread() -> None:
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_server())
        finally:
            loop.close()

    thread = Thread(target=server_thread, daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    port = int(server_info["port"])

    recorder = NetworkTraceRecorder()
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allow_loopback=True),
        trace_recorder=recorder,
    )
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    )
    node = {
        "node_id": "graphql-multi-reconnect",
        "node_kind": "network.graphql_subscription",
        "node_config": {
            "action": "connect",
            "connection_id": "graphql-multi-reconnect",
            "endpoint": f"ws://127.0.0.1:{port}/graphql",
            "query": "subscription Tick { tick }",
            "timeout_seconds": 2,
            "max_reconnect_attempts": 2,
            "reconnect_delay_seconds": 0,
            "reconnect_max_delay_seconds": 0,
        },
    }
    try:
        connected = registry.execute("network.graphql_subscription", node, context)
        received = []
        for index in range(1, 4):
            result = registry.execute(
                "network.graphql_subscription",
                {
                    **node,
                    "node_id": f"graphql-multi-reconnect-next-{index}",
                    "node_config": {
                        "action": "next_event",
                        "connection_id": "graphql-multi-reconnect",
                        "timeout_seconds": 2,
                    },
                },
                context,
            )
            assert result["status"] == "succeeded", result
            received.append(result["data"]["tick"])

        unsubscribed = registry.execute(
            "network.graphql_subscription",
            {
                **node,
                "node_id": "graphql-multi-reconnect-unsubscribe",
                "node_config": {
                    "action": "unsubscribe",
                    "connection_id": "graphql-multi-reconnect",
                },
            },
            context,
        )
        assert complete_received.wait(timeout=2)
        assert unsubscribed["status"] == "succeeded", unsubscribed
        assert unsubscribed["frame_type"] == "complete"
        assert context.flow_runtime.get("network_connections", {}).get(
            ("graphql", "graphql-multi-reconnect")
        ) is None
        traces = recorder.list_traces(debug_session_id=context.execution_session_context.session_id)
        assert traces
        trace = recorder.get_trace(traces[0]["trace_id"])
        assert trace["connections"][0]["connection_state"] == "closed"
    finally:
        context.close()
        service.close()
        stop.set()
        thread.join(timeout=2)

    assert connected["status"] == "succeeded", connected
    assert received == [1, 2, 3]
    assert int(server_info["connection_count"]) == 3
    frames = server_info["frames"]
    errors = server_info["errors"]
    assert isinstance(frames, list)
    assert isinstance(errors, list)
    assert errors == []
    assert [
        [frame["type"] for frame in connection]
        for connection in frames
    ] == [
        ["connection_init", "connection_ack", "subscribe"],
        ["connection_init", "connection_ack", "subscribe"],
        ["connection_init", "connection_ack", "subscribe", "complete"],
    ]
