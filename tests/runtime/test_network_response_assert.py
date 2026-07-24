from __future__ import annotations

from weconduct.network_runtime.resources import ResponseBodyStore
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_response_assert_validates_status_headers_text_json_duration_and_size(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    context = RuntimeContext(
        variables={
            "last_network_response": {
                "status_code": 201,
                "headers": {"Content-Type": "application/json"},
                "body_ref": store.create(b'{"result":{"id":7}}', content_type="application/json"),
                "duration_ms": 12,
                "final_url": "https://example.test/final",
            }
        }
    )
    node = {
        "node_id": "assert-response",
        "node_kind": "network.response_assert",
        "node_config": {
            "expected_status_codes": [200, 201],
            "required_headers": {"content-type": "application/json"},
            "body_contains": '"id":7',
            "json_path_equals": {"$.result.id": 7},
            "max_duration_ms": 20,
            "max_size_bytes": 1024,
        },
    }

    output = RuntimeExecutorRegistry().execute("network.response_assert", node, context)

    assert output["status"] == "succeeded"
    assert output["passed"] is True
    assert output["failed"] is False
    assert output["assertion_report"] == []


def test_response_assert_returns_structured_failure_report(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    context = RuntimeContext(
        variables={
            "last_network_response": {
                "status_code": 500,
                "headers": {"X-Trace": "actual"},
                "body_ref": store.create(b"unavailable", content_type="text/plain"),
                "duration_ms": 150,
            }
        }
    )
    node = {
        "node_id": "assert-response",
        "node_kind": "network.response_assert",
        "node_config": {
            "expected_status_codes": [200],
            "required_headers": {"x-trace": "expected"},
            "body_contains": "healthy",
            "max_duration_ms": 100,
            "max_size_bytes": 1,
        },
    }

    output = RuntimeExecutorRegistry().execute("network.response_assert", node, context)

    assert output["status"] == "failed"
    assert output["error_code"] == "network.response_assertion_failed"
    assert output["passed"] is False
    assert output["failed"] is True
    assert {item["kind"] for item in output["assertion_report"]} == {
        "status_code",
        "header",
        "body_contains",
        "duration",
        "size",
    }
