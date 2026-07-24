from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
import json
from pathlib import Path
from tempfile import mkdtemp
from typing import Iterator


MAX_IN_MEMORY_RESPONSE_BYTES = 4 * 1024 * 1024


class ResponseBodyTooLargeError(RuntimeError):
    error_code = "network.response_too_large"

    def __init__(self, *, size_bytes: int, max_bytes: int) -> None:
        super().__init__(
            f"network.response_too_large: response is {size_bytes} bytes, limit is {max_bytes} bytes"
        )


@dataclass(frozen=True)
class ResponseBodyRef:
    session_id: str
    storage_kind: str
    size_bytes: int
    content_type: str | None
    _payload: bytes | None = None
    path: Path | None = None

    def read_bytes(self, *, max_bytes: int | None = None) -> bytes:
        self._ensure_read_limit(max_bytes)
        if self.storage_kind == "memory" and self._payload is not None:
            return self._payload
        if self.path is None:
            raise RuntimeError("network.response_body_unavailable")
        return self.path.read_bytes()

    def read_text(self, encoding: str = "utf-8", *, max_bytes: int | None = None) -> str:
        return self.read_bytes(max_bytes=max_bytes).decode(encoding, errors="replace")

    def read_json(self, *, max_bytes: int | None = None) -> object:
        return json.loads(self.read_text(max_bytes=max_bytes))

    def iter_chunks(self, *, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        if self.storage_kind == "memory" and self._payload is not None:
            for offset in range(0, len(self._payload), chunk_size):
                yield self._payload[offset : offset + chunk_size]
            return
        if self.path is None:
            raise RuntimeError("network.response_body_unavailable")
        with self.path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                yield chunk

    def save_file(self, destination: Path) -> int:
        target = Path(destination)
        bytes_written = 0
        with target.open("wb") as handle:
            for chunk in self.iter_chunks():
                handle.write(chunk)
                bytes_written += len(chunk)
        return bytes_written

    def _ensure_read_limit(self, max_bytes: int | None) -> None:
        if max_bytes is None:
            return
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
            raise ValueError("max_bytes must be a non-negative integer or None")
        if self.size_bytes > max_bytes:
            raise ResponseBodyTooLargeError(size_bytes=self.size_bytes, max_bytes=max_bytes)


class ResponseBodyStore:
    def __init__(self, *, session_id: str, root_directory: Path) -> None:
        self._session_id = session_id
        self._directory = Path(
            mkdtemp(prefix=f"weconduct-{session_id}-", dir=root_directory)
        )
        self._closed = False

    def create(self, payload: bytes, *, content_type: str | None) -> ResponseBodyRef:
        if self._closed:
            raise RuntimeError("network.response_store_closed")
        if len(payload) <= MAX_IN_MEMORY_RESPONSE_BYTES:
            return ResponseBodyRef(
                session_id=self._session_id,
                storage_kind="memory",
                size_bytes=len(payload),
                content_type=content_type,
                _payload=payload,
            )
        path = self._directory / f"response-{len(list(self._directory.iterdir()))}.bin"
        path.write_bytes(payload)
        return ResponseBodyRef(
            session_id=self._session_id,
            storage_kind="file",
            size_bytes=len(payload),
            content_type=content_type,
            path=path,
        )

    async def create_from_async_chunks(
        self,
        chunks: AsyncIterable[bytes],
        *,
        content_type: str | None,
        force_file: bool = False,
    ) -> ResponseBodyRef:
        if self._closed:
            raise RuntimeError("network.response_store_closed")
        payload = bytearray()
        path: Path | None = None
        handle = None
        size_bytes = 0
        try:
            if force_file:
                path = self._next_response_path()
                handle = path.open("wb")
            async for chunk in chunks:
                if not chunk:
                    continue
                size_bytes += len(chunk)
                if path is None and len(payload) + len(chunk) <= MAX_IN_MEMORY_RESPONSE_BYTES:
                    payload.extend(chunk)
                    continue
                if path is None:
                    path = self._next_response_path()
                    handle = path.open("wb")
                    handle.write(payload)
                    payload.clear()
                handle.write(chunk)
        finally:
            if handle is not None:
                handle.close()
        if path is None:
            return ResponseBodyRef(
                session_id=self._session_id,
                storage_kind="memory",
                size_bytes=size_bytes,
                content_type=content_type,
                _payload=bytes(payload),
            )
        return ResponseBodyRef(
            session_id=self._session_id,
            storage_kind="file",
            size_bytes=size_bytes,
            content_type=content_type,
            path=path,
        )

    def _next_response_path(self) -> Path:
        return self._directory / f"response-{len(list(self._directory.iterdir()))}.bin"

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for path in self._directory.glob("*"):
            path.unlink(missing_ok=True)
        self._directory.rmdir()
