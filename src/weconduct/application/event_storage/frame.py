"""Append-frame codec for the 0.8.2 incremental event storage kernel.

Segment file layout (design doc §5):

    header  : magic "WCES" | schema_ver u16 | record_kind u8 | reserved u8
    frames  : frame_len u32 | crc32 u32 | payload (msgpack)

The frame layer only knows bytes. Higher layers (segment/session) decide what
the payload means. CRC32 guards single-frame integrity so a torn tail write is
detectable and recoverable (design doc §6.2).
"""
from __future__ import annotations

from dataclasses import dataclass
from zlib import crc32

from weconduct.packaging.msgpack_codec import packb, unpackb

MAGIC = b"WCES"
SCHEMA_VERSION = 1
HEADER_SIZE = 8

RECORD_KIND_EVENT = 1
RECORD_KIND_CHECKPOINT = 2

_FRAME_PREFIX_SIZE = 8  # frame_len(4) + crc32(4)


class FrameError(ValueError):
    """Raised when a segment header or frame is structurally invalid."""


@dataclass(frozen=True)
class SegmentHeader:
    schema_version: int
    record_kind: int


def encode_header(record_kind: int, *, schema_version: int = SCHEMA_VERSION) -> bytes:
    if record_kind not in (RECORD_KIND_EVENT, RECORD_KIND_CHECKPOINT):
        raise FrameError(f"unsupported record_kind: {record_kind}")
    if not 0 <= schema_version <= 0xFFFF:
        raise FrameError(f"schema_version out of range: {schema_version}")
    return MAGIC + schema_version.to_bytes(2, "big") + bytes((record_kind, 0))


def decode_header(data: bytes) -> SegmentHeader:
    if len(data) < HEADER_SIZE:
        raise FrameError("segment header truncated")
    if data[:4] != MAGIC:
        raise FrameError("segment magic mismatch")
    schema_version = int.from_bytes(data[4:6], "big")
    record_kind = data[6]
    if record_kind not in (RECORD_KIND_EVENT, RECORD_KIND_CHECKPOINT):
        raise FrameError(f"unsupported record_kind: {record_kind}")
    return SegmentHeader(schema_version=schema_version, record_kind=record_kind)


def encode_frame(record: object) -> bytes:
    """Encode one record into a length-prefixed, CRC-guarded frame."""
    payload = packb(record)
    if len(payload) > 0xFFFFFFFF:
        raise FrameError("frame payload exceeds u32 length")
    return len(payload).to_bytes(4, "big") + crc32(payload).to_bytes(4, "big") + payload


@dataclass(frozen=True)
class ScanResult:
    """Outcome of scanning a segment body for intact frames.

    valid_end is the offset (relative to the start of `body`) of the first byte
    after the last intact frame. Bytes past valid_end are a torn/corrupt tail
    and must be truncated before the next append (design doc §6.2).
    """

    records: list[object]
    valid_end: int
    truncated: bool


def scan_frames(body: bytes) -> ScanResult:
    """Scan a segment body (after the header) for intact frames.

    Stops at the first frame whose length overflows the buffer or whose CRC
    does not match, treating everything from there on as a torn tail.
    """
    records: list[object] = []
    offset = 0
    total = len(body)
    while offset < total:
        if offset + _FRAME_PREFIX_SIZE > total:
            return ScanResult(records=records, valid_end=offset, truncated=True)
        frame_len = int.from_bytes(body[offset : offset + 4], "big")
        expected_crc = int.from_bytes(body[offset + 4 : offset + 8], "big")
        payload_start = offset + _FRAME_PREFIX_SIZE
        payload_end = payload_start + frame_len
        if payload_end > total:
            return ScanResult(records=records, valid_end=offset, truncated=True)
        payload = body[payload_start:payload_end]
        if crc32(payload) != expected_crc:
            return ScanResult(records=records, valid_end=offset, truncated=True)
        try:
            record = unpackb(payload)
        except (ValueError, TypeError):
            return ScanResult(records=records, valid_end=offset, truncated=True)
        records.append(record)
        offset = payload_end
    return ScanResult(records=records, valid_end=offset, truncated=False)
