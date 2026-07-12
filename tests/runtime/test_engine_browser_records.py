from weconduct.runtime.engine import _append_bounded_browser_record


def test_append_bounded_browser_record_keeps_only_latest_records() -> None:
    records = [{"index": 0}, {"index": 1}]

    _append_bounded_browser_record(records, {"index": 2}, limit=2)

    assert records == [{"index": 1}, {"index": 2}]


def test_append_bounded_browser_record_uses_default_capacity() -> None:
    records: list[dict] = []

    for index in range(501):
        _append_bounded_browser_record(records, {"index": index})

    assert len(records) == 500
    assert records[0] == {"index": 1}
    assert records[-1] == {"index": 500}
