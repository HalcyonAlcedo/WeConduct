from __future__ import annotations

import pytest

from weconduct.network_runtime.resources import ResponseBodyStore, ResponseBodyTooLargeError
from weconduct.runtime.engine import RuntimeContext, _resolve_string


def test_runtime_reference_reads_bounded_json_body_and_nested_field(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    body_ref = store.create(
        b'{"files":[{"name":"report.txt"}]}',
        content_type="application/json",
    )
    context = RuntimeContext(node_outputs={"node-http": {"body_ref": body_ref}})

    assert _resolve_string(
        "${node.node-http.body_ref.read_json.files}",
        context,
    ) == [{"name": "report.txt"}]
    assert _resolve_string(
        "const files = ${node.node-http.body_ref.read_json.files};",
        context,
    ) == 'const files = [{"name": "report.txt"}];'


def test_runtime_reference_reads_bounded_text_body(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    body_ref = store.create("进度完成".encode(), content_type="text/plain; charset=utf-8")
    context = RuntimeContext(node_outputs={"node-http": {"body_ref": body_ref}})

    assert _resolve_string("${node.node-http.body_ref.read_text}", context) == "进度完成"


@pytest.mark.parametrize(
    ("payload", "content_type", "expected"),
    [
        (b'{"ok":true}', "application/json; charset=utf-8", {"ok": True}),
        (b"plain text", "text/plain", "plain text"),
        (b"invalid json", "application/json", "invalid json"),
    ],
)
def test_runtime_reference_auto_reads_body_with_legacy_content_type_semantics(
    tmp_path,
    payload: bytes,
    content_type: str,
    expected: object,
) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    body_ref = store.create(payload, content_type=content_type)
    context = RuntimeContext(node_outputs={"node-http": {"body_ref": body_ref}})

    assert _resolve_string("${node.node-http.body_ref.read_auto}", context) == expected


def test_runtime_reference_rejects_body_larger_than_four_mib(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    body_ref = store.create(
        b"x" * (4 * 1024 * 1024 + 1),
        content_type="text/plain",
    )
    context = RuntimeContext(node_outputs={"node-http": {"body_ref": body_ref}})

    with pytest.raises(ResponseBodyTooLargeError, match="network.response_too_large"):
        _resolve_string("${node.node-http.body_ref.read_text}", context)
