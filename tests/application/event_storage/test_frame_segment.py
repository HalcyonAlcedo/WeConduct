"""Fault-injection tests for the frame/segment layer (test plan §3).

Core guarantee: frames confirmed on disk are never lost; a torn/corrupt tail
is detected and truncated, and appends resume contiguously.
"""
from pathlib import Path

from weconduct.application.event_storage.frame import (
    HEADER_SIZE,
    RECORD_KIND_EVENT,
    decode_header,
    encode_frame,
)
from weconduct.application.event_storage.segment import Segment
import pytest


def _seg(tmp_path: Path) -> Segment:
    return Segment(tmp_path / "events.seg", record_kind=RECORD_KIND_EVENT)


def test_roundtrip_preserves_records(tmp_path: Path) -> None:
    seg = _seg(tmp_path)
    for i in range(5):
        seg.append({"event_index": i})
    assert [r["event_index"] for r in seg.read_all()] == [0, 1, 2, 3, 4]
    assert seg.read_range(1, 3) == [{"event_index": 1}, {"event_index": 2}]


def test_header_is_valid(tmp_path: Path) -> None:
    seg = _seg(tmp_path)
    seg.append({"a": 1})
    header = decode_header(seg.path.read_bytes()[:HEADER_SIZE])
    assert header.record_kind == RECORD_KIND_EVENT
    assert header.schema_version == 1


def test_torn_tail_partial_frame_is_recovered(tmp_path: Path) -> None:
    """C1: a partially written trailing frame is dropped; prior frames survive."""
    seg = _seg(tmp_path)
    for i in range(3):
        seg.append({"event_index": i})
    with open(seg.path, "ab") as h:
        h.write(b"\x00\x00\x00\x10partialbytes")  # len says 16, only 11 follow
    # read_all returns the intact prefix even with a torn tail present.
    assert [r["event_index"] for r in seg.read_all()] == [0, 1, 2]
    # After explicit recovery, appends resume contiguously (recover_tail is the
    # caller's responsibility once per process; append itself does not scan).
    seg.recover_tail()
    seg.append({"event_index": 3})
    assert [r["event_index"] for r in seg.read_all()] == [0, 1, 2, 3]


def test_crc_mismatch_tail_is_recovered(tmp_path: Path) -> None:
    """C2: a frame whose payload was corrupted (bad CRC) marks the tail."""
    seg = _seg(tmp_path)
    seg.append({"event_index": 0})
    good_frame = encode_frame({"event_index": 1})
    corrupt = bytearray(good_frame)
    corrupt[-1] ^= 0xFF  # flip a payload byte, CRC no longer matches
    with open(seg.path, "ab") as h:
        h.write(bytes(corrupt))
    assert [r["event_index"] for r in seg.read_all()] == [0]


def test_length_overflow_tail_is_recovered(tmp_path: Path) -> None:
    """C3: a frame_len exceeding remaining bytes does not over-read."""
    seg = _seg(tmp_path)
    seg.append({"event_index": 0})
    with open(seg.path, "ab") as h:
        h.write(b"\xff\xff\xff\xff\x00\x00\x00\x00short")
    assert [r["event_index"] for r in seg.read_all()] == [0]


def test_header_corruption_raises(tmp_path: Path) -> None:
    """C4: a bad magic is surfaced, not silently misread."""
    seg = _seg(tmp_path)
    seg.append({"event_index": 0})
    raw = bytearray(seg.path.read_bytes())
    raw[0] = 0x00  # corrupt magic
    seg.path.write_bytes(bytes(raw))
    with pytest.raises(Exception):
        seg.read_all()


def test_recover_truncates_on_disk(tmp_path: Path) -> None:
    """C6: recovery physically truncates so the next append is contiguous."""
    seg = _seg(tmp_path)
    seg.append({"event_index": 0})
    good_size = seg.path.stat().st_size
    with open(seg.path, "ab") as h:
        h.write(b"\x00\x00\x00\x40incomplete")
    seg.recover_tail()
    assert seg.path.stat().st_size == good_size
    seg.append({"event_index": 1})
    assert [r["event_index"] for r in seg.read_all()] == [0, 1]


def test_no_history_loss_across_many_appends(tmp_path: Path) -> None:
    seg = _seg(tmp_path)
    for i in range(200):
        seg.append({"event_index": i})
    assert len(seg.read_all()) == 200
