"""Append-only segment file with crash-tail recovery (design doc §6).

A segment is a header followed by CRC-guarded frames. Appends are single-frame
writes flushed with fsync; the file only grows (compaction excepted). On open,
the tail is scanned and any torn/corrupt trailing bytes are truncated so the
next append starts from the last intact frame boundary.
"""
from __future__ import annotations

from pathlib import Path

from weconduct.application.event_storage.frame import (
    HEADER_SIZE,
    ScanResult,
    decode_header,
    encode_frame,
    encode_header,
    scan_frames,
)


class Segment:
    def __init__(self, path: str | Path, *, record_kind: int) -> None:
        self._path = Path(path)
        self._record_kind = record_kind

    @property
    def path(self) -> Path:
        return self._path

    def ensure_initialized(self) -> None:
        """Create the segment with a header if it does not exist yet."""
        if self._path.exists():
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as handle:
            handle.write(encode_header(self._record_kind))
            handle.flush()
            import os

            os.fsync(handle.fileno())

    def append(self, record: object) -> None:
        """Append one record, flushed and fsynced so frame order is durable.

        Does NOT scan the file (that would make append O(n)). Tail recovery is
        the caller's responsibility once per process via recover_tail().
        """
        self.ensure_initialized()
        frame = encode_frame(record)
        import os

        with open(self._path, "ab") as handle:
            handle.write(frame)
            handle.flush()
            os.fsync(handle.fileno())

    def read_all(self) -> list[object]:
        result = self._scan()
        return result.records

    def read_range(self, start: int, end: int | None = None) -> list[object]:
        """Return records in index range [start, end) after tail recovery."""
        records = self.read_all()
        if end is None:
            return records[start:]
        return records[start:end]

    def recover_tail(self) -> ScanResult | None:
        """Truncate any torn/corrupt tail so the next append is contiguous."""
        if not self._path.exists():
            return None
        result = self._scan()
        if result.truncated:
            intact_size = HEADER_SIZE + result.valid_end
            self._truncate_to(intact_size)
        return result

    def _scan(self) -> ScanResult:
        raw = self._path.read_bytes()
        if len(raw) < HEADER_SIZE:
            # Header itself is torn: nothing intact.
            return ScanResult(records=[], valid_end=0, truncated=len(raw) > 0)
        decode_header(raw[:HEADER_SIZE])  # raises FrameError on bad magic/kind
        return scan_frames(raw[HEADER_SIZE:])

    def _truncate_to(self, size: int) -> None:
        import os

        with open(self._path, "r+b") as handle:
            handle.truncate(size)
            handle.flush()
            os.fsync(handle.fileno())
