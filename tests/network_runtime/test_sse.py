from __future__ import annotations

import asyncio

import pytest

from weconduct.network_runtime.long_connection import SSEConnection, SSEConnectionClosed


def test_sse_connection_queues_events_and_tracks_last_event_id() -> None:
    async def run() -> None:
        connection = SSEConnection(max_queue_size=2)
        await connection.feed(
            {"id": "event-1", "event": "message", "data": "{\"ok\":true}", "retry": 1500}
        )

        event = await connection.receive()

        assert event.event_id == "event-1"
        assert event.event_type == "message"
        assert event.data == '{"ok":true}'
        assert event.retry_ms == 1500
        assert connection.last_event_id == "event-1"
        assert connection.build_reconnect_headers() == {"Last-Event-ID": "event-1"}

    asyncio.run(run())


def test_sse_connection_close_wakes_receive() -> None:
    async def run() -> None:
        connection = SSEConnection()
        waiter = asyncio.create_task(connection.receive())
        await asyncio.sleep(0)
        await connection.close()

        with pytest.raises(SSEConnectionClosed):
            await waiter

    asyncio.run(run())
