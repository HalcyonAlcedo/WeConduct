from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp


MAX_IN_MEMORY_RESPONSE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class ResponseBodyRef:
    session_id: str
    storage_kind: str
    size_bytes: int
    content_type: str | None
    _payload: bytes | None = None
    path: Path | None = None

    def read_bytes(self) -> bytes:
        if self.storage_kind == "memory" and self._payload is not None:
            return self._payload
        if self.path is None:
            raise RuntimeError("network.response_body_unavailable")
        return self.path.read_bytes()

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.read_bytes().decode(encoding, errors="replace")


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

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for path in self._directory.glob("*"):
            path.unlink(missing_ok=True)
        self._directory.rmdir()
