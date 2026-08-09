from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass, field
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


@dataclass
class _ResponseBodyLease:
    closed: bool = False


@dataclass(frozen=True)
class ResponseBodyRef:
    session_id: str
    storage_kind: str
    size_bytes: int
    content_type: str | None
    _payload: bytes | None = None
    path: Path | None = None
    _lease: _ResponseBodyLease | None = field(default=None, repr=False, compare=False)

    def read_bytes(self, *, max_bytes: int | None = None) -> bytes:
        self._ensure_available()
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
        self._ensure_available()
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

    def _ensure_available(self) -> None:
        if self._lease is not None and self._lease.closed:
            raise RuntimeError("network.response_body_unavailable")


class ResponseBodyStore:
    def __init__(self, *, session_id: str, root_directory: Path) -> None:
        self._session_id = session_id
        self._directory = Path(
            mkdtemp(prefix=f"weconduct-{session_id}-", dir=root_directory)
        )
        self._closed = False
        self._lease = _ResponseBodyLease()

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
                _lease=self._lease,
            )
        path = self._directory / f"response-{len(list(self._directory.iterdir()))}.bin"
        path.write_bytes(payload)
        return ResponseBodyRef(
            session_id=self._session_id,
            storage_kind="file",
            size_bytes=len(payload),
            content_type=content_type,
            path=path,
            _lease=self._lease,
        )

    async def create_from_async_chunks(
        self,
        chunks: AsyncIterable[bytes],
        *,
        content_type: str | None,
        force_file: bool = False,
        max_bytes: int | None = None,
        max_in_memory_bytes: int | None = None,
    ) -> ResponseBodyRef:
        if self._closed:
            raise RuntimeError("network.response_store_closed")
        _validate_response_limit(max_bytes, "max_bytes")
        _validate_response_limit(max_in_memory_bytes, "max_in_memory_bytes")
        memory_limit = (
            MAX_IN_MEMORY_RESPONSE_BYTES
            if max_in_memory_bytes is None
            else max_in_memory_bytes
        )
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
                if max_bytes is not None and size_bytes > max_bytes:
                    raise ResponseBodyTooLargeError(size_bytes=size_bytes, max_bytes=max_bytes)
                if path is None and len(payload) + len(chunk) <= memory_limit:
                    payload.extend(chunk)
                    continue
                if path is None:
                    path = self._next_response_path()
                    handle = path.open("wb")
                    handle.write(payload)
                    payload.clear()
                handle.write(chunk)
        except BaseException:
            if handle is not None:
                handle.close()
            if path is not None:
                path.unlink(missing_ok=True)
            raise
        else:
            if handle is not None:
                handle.close()
        if path is None:
            return ResponseBodyRef(
                session_id=self._session_id,
                storage_kind="memory",
                size_bytes=size_bytes,
                content_type=content_type,
                _payload=bytes(payload),
                _lease=self._lease,
            )
        return ResponseBodyRef(
            session_id=self._session_id,
            storage_kind="file",
            size_bytes=size_bytes,
            content_type=content_type,
            path=path,
            _lease=self._lease,
        )

    def _next_response_path(self) -> Path:
        return self._directory / f"response-{len(list(self._directory.iterdir()))}.bin"

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._lease.closed = True
        for path in self._directory.glob("*"):
            path.unlink(missing_ok=True)
        self._directory.rmdir()


def _validate_response_limit(value: int | None, name: str) -> None:
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer or None")
