from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from tempfile import mkdtemp
from threading import Thread
from time import sleep
from typing import Iterator
from uuid import uuid4


MAX_IN_MEMORY_RESPONSE_BYTES = 4 * 1024 * 1024
_DEFERRED_CLEANUP_ATTEMPTS = 200
_DEFERRED_CLEANUP_INTERVAL_SECONDS = 0.05


class ResponseBodyTooLargeError(RuntimeError):
    error_code = "network.response_too_large"

    def __init__(self, *, size_bytes: int, max_bytes: int) -> None:
        super().__init__(
            f"network.response_too_large: response is {size_bytes} bytes, limit is {max_bytes} bytes"
        )


@dataclass
class _ResponseBodyEntry:
    resource_id: str
    storage_kind: str
    size_bytes: int
    content_type: str | None
    sha256: str
    payload: bytes | None = None
    path: Path | None = None
    closed: bool = False
    ref_count: int = 0


@dataclass
class _ResponseBodyLease:
    closed: bool = False
    entries: dict[str, _ResponseBodyEntry] = field(default_factory=dict)


@dataclass(frozen=True)
class ResponseBodyRef:
    session_id: str
    storage_kind: str
    size_bytes: int
    content_type: str | None
    resource_id: str = ""
    sha256: str = ""
    _payload: bytes | None = None
    path: Path | None = None
    _lease: _ResponseBodyLease | None = field(default=None, repr=False, compare=False)

    def read_bytes(self, *, max_bytes: int | None = None) -> bytes:
        entry = self._ensure_available()
        self._ensure_read_limit(max_bytes)
        if entry.storage_kind == "memory" and entry.payload is not None:
            return entry.payload
        if entry.path is None:
            raise RuntimeError("network.response_body_unavailable")
        return entry.path.read_bytes()

    def read_text(self, encoding: str = "utf-8", *, max_bytes: int | None = None) -> str:
        return self.read_bytes(max_bytes=max_bytes).decode(encoding, errors="replace")

    def read_json(self, *, max_bytes: int | None = None) -> object:
        return json.loads(self.read_text(max_bytes=max_bytes))

    def iter_chunks(self, *, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        entry = self._ensure_available()
        if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        if entry.storage_kind == "memory" and entry.payload is not None:
            for offset in range(0, len(entry.payload), chunk_size):
                yield entry.payload[offset : offset + chunk_size]
            return
        if entry.path is None:
            raise RuntimeError("network.response_body_unavailable")
        with entry.path.open("rb") as handle:
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

    def release(self) -> None:
        lease = self._lease
        if lease is None:
            return
        entry = lease.entries.get(self.resource_id)
        if entry is None or entry.closed:
            return
        entry.ref_count -= 1
        if entry.ref_count <= 0:
            entry.closed = True
            if entry.path is not None:
                entry.path.unlink(missing_ok=True)

    def to_debug_descriptor(self) -> dict[str, object]:
        available = False
        lease = self._lease
        if lease is None:
            available = self._payload is not None or self.path is None or self.path.exists()
        else:
            entry = lease.entries.get(self.resource_id)
            available = bool(entry is not None and not lease.closed and not entry.closed)
        path_text = str(self.path) if self.path is not None else None
        return {
            "resource_kind": "session_temp",
            "resource_id": self.resource_id or None,
            "session_id": self.session_id,
            "storage_kind": self.storage_kind,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "sha256": self.sha256 or None,
            "available": available,
            "path": path_text,
        }

    def _ensure_read_limit(self, max_bytes: int | None) -> None:
        if max_bytes is None:
            return
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
            raise ValueError("max_bytes must be a non-negative integer or None")
        if self.size_bytes > max_bytes:
            raise ResponseBodyTooLargeError(size_bytes=self.size_bytes, max_bytes=max_bytes)

    def _ensure_available(self) -> _ResponseBodyEntry:
        if self._lease is None:
            if self.storage_kind == "memory" and self._payload is not None:
                return _ResponseBodyEntry(
                    resource_id=self.resource_id or "standalone-memory",
                    storage_kind="memory",
                    size_bytes=self.size_bytes,
                    content_type=self.content_type,
                    sha256=self.sha256,
                    payload=self._payload,
                    path=None,
                )
            if self.path is not None and self.path.exists():
                return _ResponseBodyEntry(
                    resource_id=self.resource_id or "standalone-file",
                    storage_kind="file",
                    size_bytes=self.size_bytes,
                    content_type=self.content_type,
                    sha256=self.sha256,
                    payload=None,
                    path=self.path,
                )
            raise RuntimeError("network.response_body_unavailable")
        if self._lease.closed:
            raise RuntimeError("network.response_body_unavailable")
        entry = self._lease.entries.get(self.resource_id)
        if entry is None or entry.closed:
            raise RuntimeError("network.response_body_unavailable")
        return entry


class _ResponseBodyCapture:
    def __init__(
        self,
        *,
        store: ResponseBodyStore,
        content_type: str | None,
        force_file: bool = False,
        max_in_memory_bytes: int | None = None,
    ) -> None:
        self._store = store
        self._content_type = content_type
        self._force_file = force_file
        self._memory_limit = (
            MAX_IN_MEMORY_RESPONSE_BYTES
            if max_in_memory_bytes is None
            else max_in_memory_bytes
        )
        self._payload = bytearray()
        self._path: Path | None = None
        self._handle = None
        self._size_bytes = 0
        self._sha256 = hashlib.sha256()
        self._closed = False

    @property
    def size_bytes(self) -> int:
        return self._size_bytes

    def write(self, chunk: bytes) -> None:
        if self._closed:
            raise RuntimeError("network.response_store_closed")
        if not chunk:
            return
        self._size_bytes += len(chunk)
        self._sha256.update(chunk)
        if self._path is None and not self._force_file and len(self._payload) + len(chunk) <= self._memory_limit:
            self._payload.extend(chunk)
            return
        if self._path is None:
            self._path = self._store._next_response_path()
            self._handle = self._path.open("wb")
            if self._payload:
                self._handle.write(self._payload)
                self._payload.clear()
        assert self._handle is not None
        self._handle.write(chunk)

    def finish(self) -> ResponseBodyRef:
        if self._closed:
            raise RuntimeError("network.response_store_closed")
        self._closed = True
        if self._handle is not None:
            self._handle.close()
        payload: bytes | None = None
        storage_kind = "file"
        path = self._path
        if path is None:
            storage_kind = "memory"
            payload = bytes(self._payload)
        return self._store._register_entry(
            storage_kind=storage_kind,
            size_bytes=self._size_bytes,
            content_type=self._content_type,
            sha256=self._sha256.hexdigest(),
            payload=payload,
            path=path,
        )

    def abort(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._handle is not None:
            self._handle.close()
        if self._path is not None:
            self._path.unlink(missing_ok=True)


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
        storage_kind = "memory" if len(payload) <= MAX_IN_MEMORY_RESPONSE_BYTES else "file"
        path: Path | None = None
        stored_payload: bytes | None = payload
        if storage_kind == "file":
            path = self._next_response_path()
            path.write_bytes(payload)
            stored_payload = None
        return self._register_entry(
            storage_kind=storage_kind,
            size_bytes=len(payload),
            content_type=content_type,
            sha256=hashlib.sha256(payload).hexdigest(),
            payload=stored_payload,
            path=path,
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
        capture = self.open_capture(
            content_type=content_type,
            force_file=force_file,
            max_in_memory_bytes=max_in_memory_bytes,
        )
        try:
            async for chunk in chunks:
                if not chunk:
                    continue
                capture.write(chunk)
                if max_bytes is not None and capture.size_bytes > max_bytes:
                    raise ResponseBodyTooLargeError(size_bytes=capture.size_bytes, max_bytes=max_bytes)
        except BaseException:
            capture.abort()
            raise
        return capture.finish()

    def create_from_file_copy(self, source: Path, *, content_type: str | None) -> ResponseBodyRef:
        if self._closed:
            raise RuntimeError("network.response_store_closed")
        path = Path(source)
        capture = self.open_capture(content_type=content_type, force_file=True)
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                capture.write(chunk)
        return capture.finish()

    def open_capture(
        self,
        *,
        content_type: str | None,
        force_file: bool = False,
        max_in_memory_bytes: int | None = None,
    ) -> _ResponseBodyCapture:
        if self._closed:
            raise RuntimeError("network.response_store_closed")
        _validate_response_limit(max_in_memory_bytes, "max_in_memory_bytes")
        return _ResponseBodyCapture(
            store=self,
            content_type=content_type,
            force_file=force_file,
            max_in_memory_bytes=max_in_memory_bytes,
        )

    def retain(self, body_ref: ResponseBodyRef) -> ResponseBodyRef:
        if self._closed:
            raise RuntimeError("network.response_store_closed")
        entry = self._lease.entries.get(body_ref.resource_id)
        if entry is None or entry.closed:
            raise RuntimeError("network.response_body_unavailable")
        entry.ref_count += 1
        return ResponseBodyRef(
            session_id=self._session_id,
            storage_kind=entry.storage_kind,
            size_bytes=entry.size_bytes,
            content_type=entry.content_type,
            resource_id=entry.resource_id,
            sha256=entry.sha256,
            _payload=entry.payload,
            path=entry.path,
            _lease=self._lease,
        )

    def read_debug_descriptor(self, descriptor: dict) -> bytes:
        """按已登记的资源 ID 读取 Debug 正文，拒绝伪造路径或元数据。"""
        if not isinstance(descriptor, dict):
            raise RuntimeError("network.response_body_unavailable")
        if (
            descriptor.get("resource_kind") != "session_temp"
            or descriptor.get("session_id") != self._session_id
        ):
            raise RuntimeError("network.response_body_unavailable")
        resource_id = descriptor.get("resource_id")
        if (
            not isinstance(resource_id, str)
            or not resource_id.strip()
            or resource_id in {".", ".."}
            or "/" in resource_id
            or "\\" in resource_id
        ):
            raise RuntimeError("network.response_body_unavailable")
        if self._closed or self._lease.closed:
            raise RuntimeError("network.response_body_unavailable")
        entry = self._lease.entries.get(resource_id)
        if entry is None or entry.closed:
            raise RuntimeError("network.response_body_unavailable")
        storage_kind = descriptor.get("storage_kind")
        if isinstance(storage_kind, str) and storage_kind != entry.storage_kind:
            raise RuntimeError("network.response_body_unavailable")
        size_bytes = descriptor.get("size_bytes")
        if (
            isinstance(size_bytes, int)
            and not isinstance(size_bytes, bool)
            and size_bytes != entry.size_bytes
        ):
            raise RuntimeError("network.response_body_unavailable")
        sha256 = descriptor.get("sha256")
        if isinstance(sha256, str) and sha256.strip() and sha256 != entry.sha256:
            raise RuntimeError("network.response_body_unavailable")
        descriptor_path = descriptor.get("path")
        if entry.path is None:
            if descriptor_path not in {None, ""} or entry.payload is None:
                raise RuntimeError("network.response_body_unavailable")
            payload = entry.payload
        else:
            if not isinstance(descriptor_path, str) or not descriptor_path.strip():
                raise RuntimeError("network.response_body_unavailable")
            try:
                if Path(descriptor_path).resolve(strict=True) != entry.path.resolve(strict=True):
                    raise RuntimeError("network.response_body_unavailable")
                payload = entry.path.read_bytes()
            except (OSError, RuntimeError) as exc:
                if isinstance(exc, RuntimeError):
                    raise
                raise RuntimeError("network.response_body_unavailable") from exc
        if len(payload) != entry.size_bytes or hashlib.sha256(payload).hexdigest() != entry.sha256:
            raise RuntimeError("network.response_body_unavailable")
        return payload

    def _register_entry(
        self,
        *,
        storage_kind: str,
        size_bytes: int,
        content_type: str | None,
        sha256: str,
        payload: bytes | None,
        path: Path | None,
    ) -> ResponseBodyRef:
        resource_id = f"body-{uuid4().hex}"
        entry = _ResponseBodyEntry(
            resource_id=resource_id,
            storage_kind=storage_kind,
            size_bytes=size_bytes,
            content_type=content_type,
            sha256=sha256,
            payload=payload,
            path=path,
            ref_count=1,
        )
        self._lease.entries[resource_id] = entry
        return ResponseBodyRef(
            session_id=self._session_id,
            storage_kind=storage_kind,
            size_bytes=size_bytes,
            content_type=content_type,
            resource_id=resource_id,
            sha256=sha256,
            _payload=payload,
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
        pending_paths: list[Path] = []
        for entry in self._lease.entries.values():
            entry.closed = True
            if entry.path is not None:
                try:
                    entry.path.unlink(missing_ok=True)
                except OSError:
                    # Windows 读句柄未释放时暂时无法删除，交给后台重试，
                    # 避免会话关闭因 WinError 32 失败。
                    pending_paths.append(entry.path)
        self._lease.entries.clear()
        for path in self._directory.glob("*"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pending_paths.append(path)
        try:
            self._directory.rmdir()
        except OSError:
            pending_paths.append(self._directory)
        if pending_paths:
            self._schedule_deferred_cleanup(pending_paths)

    def _schedule_deferred_cleanup(self, pending_paths: list[Path]) -> None:
        paths = tuple(dict.fromkeys(pending_paths))
        Thread(
            target=_retry_deferred_cleanup,
            args=(paths,),
            daemon=True,
            name="weconduct-response-cleanup",
        ).start()


def _validate_response_limit(value: int | None, name: str) -> None:
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer or None")


def _retry_deferred_cleanup(paths: tuple[Path, ...]) -> None:
    """重试被 Windows 读句柄暂时锁定的正文文件及其会话目录。"""
    pending = set(paths)
    for attempt in range(_DEFERRED_CLEANUP_ATTEMPTS):
        for path in tuple(pending):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    continue
            else:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    continue
            pending.discard(path)
        directories = {path for path in pending if path.is_dir()}
        for directory in tuple(directories):
            try:
                for child in directory.glob("*"):
                    pending.add(child)
                if not any(directory.iterdir()):
                    directory.rmdir()
                    pending.discard(directory)
            except OSError:
                continue
        if not pending:
            return
        if attempt + 1 < _DEFERRED_CLEANUP_ATTEMPTS:
            sleep(_DEFERRED_CLEANUP_INTERVAL_SECONDS)
