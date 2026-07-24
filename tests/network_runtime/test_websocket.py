from __future__ import annotations

import asyncio

import pytest

from weconduct.network_runtime.long_connection import WebSocketConnection, WebSocketConnectionError


def test_websocket_connection_delegates_pull_operations_and_tracks_epoch() -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.sent: list[object] = []
            self.closed = False

        async def send(self, value: object) -> None:
            self.sent.append(value)

        async def recv(self) -> object:
            return "incoming"

        async def ping(self, value: bytes | None = None) -> None:
            self.sent.append(("ping", value))

        async def close(self) -> None:
            self.closed = True

    async def run() -> None:
        socket = FakeSocket()
        connection = WebSocketConnection(socket)

        await connection.send("outgoing")
        assert await connection.receive() == "incoming"
        await connection.ping(b"keepalive")
        assert connection.connection_epoch == 1
        await connection.close()

        assert socket.closed is True
        with pytest.raises(WebSocketConnectionError, match="closed"):
            await connection.send("after-close")

    asyncio.run(run())


def test_websocket_connection_reconnect_increments_epoch() -> None:
    class FakeSocket:
        async def close(self) -> None:
            return

    async def run() -> None:
        connection = WebSocketConnection(FakeSocket())
        await connection.replace_socket(FakeSocket())
        assert connection.connection_epoch == 2

    asyncio.run(run())
