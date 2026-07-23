from __future__ import annotations

import asyncio

from weconduct.network_runtime.resources import ResponseBodyStore


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
