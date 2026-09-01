from __future__ import annotations

import asyncio

import pytest

from weconduct.network_runtime.queue import (
    BoundedMessageQueue,
    ExecutionActivationQueue,
    SequenceAllocator,
    QueueBackpressureError,
    QueueCancelledError,
    QueueClosedError,
)


def _run(coro):
    return asyncio.run(coro)


def test_bounded_message_queue_preserves_fifo_and_assigns_global_sequence_ids() -> None:
    async def scenario() -> None:
        queue = BoundedMessageQueue(maxsize=4)

        await queue.put("alpha", connection_id="connection-1")
        await queue.put("beta", connection_id="connection-2")

        first = await queue.get()
        second = await queue.get()

        assert first["sequence_id"] == 1
        assert first["payload"] == "alpha"
        assert first["connection_id"] == "connection-1"
        assert second["sequence_id"] == 2
        assert second["payload"] == "beta"
        assert second["connection_id"] == "connection-2"
        assert queue.dropped_count == 0

    _run(scenario())


def test_bounded_message_queue_drop_oldest_discards_the_oldest_item() -> None:
    async def scenario() -> None:
        queue = BoundedMessageQueue(maxsize=2, backpressure_policy="drop_oldest")

        await queue.put("one")
        await queue.put("two")
        await queue.put("three")

        first = await queue.get()
        second = await queue.get()

        assert first["payload"] == "two"
        assert first["sequence_id"] == 2
        assert second["payload"] == "three"
        assert second["sequence_id"] == 3
        assert queue.dropped_count == 1

    _run(scenario())


def test_bounded_message_queue_drop_newest_discards_the_new_item() -> None:
    async def scenario() -> None:
        queue = BoundedMessageQueue(maxsize=2, backpressure_policy="drop_newest")

        await queue.put("one")
        await queue.put("two")
        await queue.put("three")

        first = await queue.get()
        second = await queue.get()

        assert first["payload"] == "one"
        assert first["sequence_id"] == 1
        assert second["payload"] == "two"
        assert second["sequence_id"] == 2
        assert queue.dropped_count == 1

    _run(scenario())


def test_bounded_message_queue_fail_stream_raises_when_full() -> None:
    async def scenario() -> None:
        queue = BoundedMessageQueue(maxsize=1, backpressure_policy="fail_stream")

        await queue.put("one")

        with pytest.raises(QueueBackpressureError):
            await queue.put("two")

        assert queue.dropped_count == 0

    _run(scenario())


def test_bounded_message_queue_close_connection_closes_on_overflow() -> None:
    async def scenario() -> None:
        queue = BoundedMessageQueue(maxsize=1, backpressure_policy="close_connection")

        await queue.put("one")

        with pytest.raises(QueueClosedError):
            await queue.put("two")

        assert queue.closed is True

        first = await queue.get()
        assert first["payload"] == "one"

        with pytest.raises(QueueClosedError):
            await queue.get()

    _run(scenario())


def test_bounded_message_queue_records_structured_drop_events() -> None:
    async def scenario() -> None:
        oldest = BoundedMessageQueue(maxsize=1, backpressure_policy="drop_oldest")
        await oldest.put("first", connection_id="connection-1", connection_epoch=2)
        await oldest.put("second", connection_id="connection-1", connection_epoch=2)
        assert oldest.drop_events == [
            {
                "event_kind": "network.queue_message_dropped",
                "policy": "drop_oldest",
                "dropped_count": 1,
                "first_sequence_id": 1,
                "last_sequence_id": 1,
                "connection_id": "connection-1",
                "connection_epoch": 2,
            }
        ]

        newest = BoundedMessageQueue(maxsize=1, backpressure_policy="drop_newest")
        await newest.put("first", connection_id="connection-2", connection_epoch=4)
        await newest.put("second", connection_id="connection-2", connection_epoch=4)
        assert newest.drop_events[0]["first_sequence_id"] == 2
        assert newest.drop_events[0]["last_sequence_id"] == 2
        assert newest.drop_events[0]["connection_id"] == "connection-2"

        close = BoundedMessageQueue(maxsize=1, backpressure_policy="close_connection")
        await close.put("first", connection_id="connection-3", connection_epoch=7)
        with pytest.raises(QueueClosedError):
            await close.put("second", connection_id="connection-3", connection_epoch=7)
        assert close.drop_events[0]["policy"] == "close_connection"
        assert close.drop_events[0]["first_sequence_id"] == 2
        assert close.drop_events[0]["connection_epoch"] == 7

    _run(scenario())


def test_bounded_message_queue_cancel_wakes_waiters() -> None:
    async def scenario() -> None:
        queue = BoundedMessageQueue(maxsize=1)

        waiter = asyncio.create_task(queue.get())
        await asyncio.sleep(0)
        queue.cancel()

        with pytest.raises(QueueCancelledError):
            await waiter

        with pytest.raises(QueueCancelledError):
            await queue.get()

    _run(scenario())


def test_execution_activation_queue_exposes_activation_aliases() -> None:
    async def scenario() -> None:
        queue = ExecutionActivationQueue(maxsize=2, backpressure_policy="drop_oldest")

        await queue.activate({"node_id": "node-1"})
        await queue.activate({"node_id": "node-2"})

        activation = await queue.wait_next()
        assert activation["sequence_id"] == 1
        assert activation["payload"]["node_id"] == "node-1"

        activation = await queue.wait_next()
        assert activation["sequence_id"] == 2
        assert activation["payload"]["node_id"] == "node-2"

    _run(scenario())


def test_message_queues_can_share_a_thread_safe_global_sequence_allocator() -> None:
    async def scenario() -> None:
        allocator = SequenceAllocator()
        first = BoundedMessageQueue(maxsize=2, sequence_allocator=allocator)
        second = BoundedMessageQueue(maxsize=2, sequence_allocator=allocator)

        first_record = await first.put("first", connection_id="connection-1")
        second_record = await second.put("second", connection_id="connection-2")

        assert first_record is not None
        assert second_record is not None
        assert first_record["sequence_id"] == 1
        assert second_record["sequence_id"] == 2

    _run(scenario())


def test_activation_can_reuse_the_source_message_sequence_id() -> None:
    async def scenario() -> None:
        queue = ExecutionActivationQueue(maxsize=2)

        activation = await queue.activate(
            {"event_kind": "sse.message"},
            sequence_id=17,
        )

        assert activation is not None
        assert activation["sequence_id"] == 17

    _run(scenario())
