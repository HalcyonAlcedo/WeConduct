from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from time import monotonic, sleep

import pytest

from weconduct.network_runtime.resources import ResponseBodyStore, ResponseBodyTooLargeError


def test_response_body_store_spills_payload_larger_than_four_mib_to_session_file(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    payload = b"x" * (4 * 1024 * 1024 + 1)

    body_ref = store.create(payload, content_type="application/octet-stream")

    assert body_ref.storage_kind == "file"
    assert body_ref.size_bytes == len(payload)
    assert body_ref.read_bytes() == payload
    store.close()
    assert body_ref.path is not None
    assert body_ref.path.exists() is False


def test_memory_response_ref_cannot_be_read_after_its_session_store_closes(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    body_ref = store.create(b"session-only", content_type="text/plain")

    store.close()

    with pytest.raises(RuntimeError, match="network.response_body_unavailable"):
        body_ref.read_bytes()


def test_response_body_store_streams_large_async_payload_to_session_file(tmp_path) -> None:
    async def chunks():
        for _ in range(5):
            yield b"x" * 1024 * 1024

    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)

    body_ref = asyncio.run(
        store.create_from_async_chunks(chunks(), content_type="application/octet-stream")
    )

    assert body_ref.storage_kind == "file"
    assert body_ref.size_bytes == 5 * 1024 * 1024
    assert body_ref.read_bytes() == b"x" * 5 * 1024 * 1024


def test_response_body_store_can_force_small_stream_to_a_session_file(tmp_path) -> None:
    async def chunks():
        yield b"small payload"

    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    body_ref = asyncio.run(
        store.create_from_async_chunks(
            chunks(),
            content_type="text/plain",
            force_file=True,
        )
    )

    assert body_ref.storage_kind == "file"
    assert body_ref.path is not None
    assert body_ref.path.read_bytes() == b"small payload"


def test_response_body_store_applies_response_limits_and_cleans_partial_file(tmp_path) -> None:
    async def chunks():
        yield b"first-chunk"
        yield b"second-chunk"

    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)

    with pytest.raises(ResponseBodyTooLargeError, match="network.response_too_large"):
        asyncio.run(
            store.create_from_async_chunks(
                chunks(),
                content_type="application/octet-stream",
                force_file=True,
                max_bytes=16,
            )
        )

    assert list(store._directory.iterdir()) == []
    store.close()


def test_response_body_store_treats_zero_max_bytes_as_no_response_body(tmp_path) -> None:
    async def chunks():
        yield b"one-byte"

    store = ResponseBodyStore(session_id="session-zero-limit", root_directory=tmp_path)

    with pytest.raises(ResponseBodyTooLargeError, match="network.response_too_large"):
        asyncio.run(
            store.create_from_async_chunks(
                chunks(),
                content_type="application/octet-stream",
                max_bytes=0,
            )
        )

    assert list(store._directory.iterdir()) == []
    store.close()


def test_response_body_store_treats_zero_memory_limit_as_force_file(tmp_path) -> None:
    async def chunks():
        yield b"small payload"

    store = ResponseBodyStore(session_id="session-zero-memory", root_directory=tmp_path)
    body_ref = asyncio.run(
        store.create_from_async_chunks(
            chunks(),
            content_type="text/plain",
            max_in_memory_bytes=0,
        )
    )

    assert body_ref.storage_kind == "file"
    assert body_ref.read_bytes() == b"small payload"


def test_response_body_store_uses_configured_memory_threshold(tmp_path) -> None:
    async def chunks():
        yield b"small payload"

    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    body_ref = asyncio.run(
        store.create_from_async_chunks(
            chunks(),
            content_type="text/plain",
            max_in_memory_bytes=1,
        )
    )

    assert body_ref.storage_kind == "file"
    assert body_ref.read_bytes() == b"small payload"


def test_response_body_ref_enforces_caller_read_limit_and_supports_streaming_helpers(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    body_ref = store.create(b'{"message":"hello"}', content_type="application/json")

    with pytest.raises(ResponseBodyTooLargeError, match="network.response_too_large"):
        body_ref.read_bytes(max_bytes=8)

    assert body_ref.read_json(max_bytes=64) == {"message": "hello"}
    assert list(body_ref.iter_chunks(chunk_size=5)) == [
        b'{"mes',
        b'sage"',
        b':"hel',
        b'lo"}',
    ]
    output_path = tmp_path / "downloaded.json"
    assert body_ref.save_file(output_path) == len(b'{"message":"hello"}')
    assert output_path.read_bytes() == b'{"message":"hello"}'


def test_response_body_ref_enforces_read_limit_for_file_backed_response(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    body_ref = store.create(b"x" * (4 * 1024 * 1024 + 1), content_type=None)

    with pytest.raises(ResponseBodyTooLargeError, match="network.response_too_large"):
        body_ref.read_text(max_bytes=1024)


def test_response_body_store_can_retain_references_and_export_debug_descriptor(tmp_path) -> None:
    payload = b"trace-payload"
    store = ResponseBodyStore(session_id="session-trace", root_directory=tmp_path)

    body_ref = store.create(payload, content_type="application/octet-stream")
    retained = store.retain(body_ref)
    descriptor = retained.to_debug_descriptor()

    assert retained.resource_id == body_ref.resource_id
    assert descriptor["resource_kind"] == "session_temp"
    assert descriptor["resource_id"] == body_ref.resource_id
    assert descriptor["size_bytes"] == len(payload)
    assert descriptor["sha256"] == hashlib.sha256(payload).hexdigest()
    assert descriptor["available"] is True

    body_ref.release()
    assert retained.read_bytes() == payload

    retained.release()
    with pytest.raises(RuntimeError, match="network.response_body_unavailable"):
        retained.read_bytes()

    store.close()


def test_response_body_store_rejects_unregistered_debug_descriptor(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-registered", root_directory=tmp_path)
    body_ref = store.create(b"registered", content_type="text/plain")
    descriptor = body_ref.to_debug_descriptor()

    assert store.read_debug_descriptor(descriptor) == b"registered"

    forged = {
        **descriptor,
        "resource_id": "body-not-registered",
        "sha256": hashlib.sha256(b"forged").hexdigest(),
    }
    with pytest.raises(RuntimeError, match="network.response_body_unavailable"):
        store.read_debug_descriptor(forged)

    store.close()


def test_response_body_store_defers_cleanup_when_windows_reader_holds_file(tmp_path) -> None:
    """关闭会话时若正文仍被 Windows 读句柄占用，清理应延后而不是失败。"""
    store = ResponseBodyStore(session_id="session-open-reader", root_directory=tmp_path)
    body_ref = store.create(b"x" * (4 * 1024 * 1024 + 1), content_type="application/octet-stream")

    assert body_ref.path is not None
    body_path = body_ref.path
    reader = body_path.open("rb")
    try:
        store.close()
    finally:
        reader.close()

    deadline = monotonic() + 2
    while (body_path.exists() or any(tmp_path.iterdir())) and monotonic() < deadline:
        sleep(0.02)

    assert body_path.exists() is False
    assert list(tmp_path.iterdir()) == []
