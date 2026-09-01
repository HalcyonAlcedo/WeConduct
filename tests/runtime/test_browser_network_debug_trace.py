from __future__ import annotations

import weconduct.runtime.engine as engine_module
from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.service import NetworkRuntimeService
from weconduct.network_runtime.trace import NetworkTraceRecorder, TRACE_MESSAGE_BODY_THRESHOLD_BYTES
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry
from weconduct.runtime.execution_context import ExecutionSessionContext


def _context(*, recorder: NetworkTraceRecorder, browser_runtime: dict) -> RuntimeContext:
    return RuntimeContext(
        browser_runtime=browser_runtime,
        flow_runtime={
            "network_trace_recorder": recorder,
            "debug_event_index_supplier": lambda: 5,
        },
        execution_session_context=ExecutionSessionContext(
            session_id="debug-browser-listener",
        ),
    )


def test_browser_wait_for_request_is_recorded_in_debug_network_trace() -> None:
    recorder = NetworkTraceRecorder()
    context = _context(
        recorder=recorder,
        browser_runtime={
            "request_records": [
                {
                    "url": "https://example.test/items",
                    "method": "POST",
                    "headers": {"x-api-key": "listener-secret"},
                    "resource_type": "fetch",
                    "post_data": '{"name":"item"}',
                }
            ]
        },
    )

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_request",
        {
            "node_id": "node-wait-request",
            "node_kind": "browser.wait_for_request",
            "node_config": {"url_pattern": "/items", "timeout": 1},
        },
        context,
    )

    assert result["status"] == "succeeded"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert len(traces) == 2
    operation = traces[0]
    assert operation["protocol"] == "browser"
    assert operation["operation_id"] == "node-wait-request"
    assert operation["debug_event_index"] == 5
    assert operation["request_headers"]["x-api-key"] == "listener-secret"
    assert operation["request_body"]["value"] == '{"name":"item"}'
    assert traces[1]["event_kind"] == "browser.request_observed"


def test_browser_wait_for_request_timeout_is_recorded_as_failed_network_trace() -> None:
    recorder = NetworkTraceRecorder()
    context = _context(
        recorder=recorder,
        browser_runtime={
            "page": type("FakePage", (), {"url": "https://example.test/items"})(),
            "request_records": [],
        },
    )

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_request",
        {
            "node_id": "node-wait-request-timeout",
            "node_kind": "browser.wait_for_request",
            "node_config": {"url_pattern": "/missing", "timeout": 0},
        },
        context,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "browser.request_timeout"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert len(traces) == 2
    assert traces[0]["status"] == "failed"
    assert traces[0]["error_code"] == "browser.request_timeout"
    assert traces[0]["method"] == "REQUEST"
    assert traces[1]["event_kind"] == "browser.request_failed"
    assert traces[1]["payload"]["url_pattern"] == "/missing"


def test_browser_wait_for_response_timeout_is_recorded_as_failed_network_trace() -> None:
    recorder = NetworkTraceRecorder()
    context = _context(
        recorder=recorder,
        browser_runtime={
            "page": type("FakePage", (), {"url": "https://example.test/items"})(),
            "response_records": [],
        },
    )

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_response",
        {
            "node_id": "node-wait-response-timeout",
            "node_kind": "browser.wait_for_response",
            "node_config": {"url_pattern": "/missing", "timeout": 0},
        },
        context,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "browser.response_timeout"
    trace = recorder.get_trace(
        recorder.list_traces(debug_session_id="debug-browser-listener")[0]["trace_id"]
    )
    assert trace["operation"]["status"] == "failed"
    assert trace["operation"]["error_code"] == "browser.response_timeout"
    assert trace["messages"][0]["event_kind"] == "browser.response_failed"


def test_browser_wait_for_popup_timeout_is_recorded_as_failed_network_trace() -> None:
    recorder = NetworkTraceRecorder()
    context = _context(
        recorder=recorder,
        browser_runtime={
            "page": type("FakePage", (), {"url": "https://example.test/items"})(),
            "popup_records": [],
        },
    )

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_popup",
        {
            "node_id": "node-wait-popup-timeout",
            "node_kind": "browser.wait_for_popup",
            "node_config": {"timeout": 0},
        },
        context,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "browser.popup_timeout"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert traces[0]["error_code"] == "browser.popup_timeout"
    assert traces[1]["event_kind"] == "browser.popup_failed"


def test_browser_wait_for_download_timeout_is_recorded_as_failed_network_trace() -> None:
    recorder = NetworkTraceRecorder()
    context = _context(
        recorder=recorder,
        browser_runtime={
            "page": type("FakePage", (), {"url": "https://example.test/items"})(),
            "download_records": [],
        },
    )
    registry = RuntimeExecutorRegistry(runtime_settings={"allow_browser_downloads": True})

    result = registry.execute(
        "browser.wait_for_download",
        {
            "node_id": "node-wait-download-timeout",
            "node_kind": "browser.wait_for_download",
            "node_config": {"timeout": 0},
        },
        context,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "browser.download_timeout"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert traces[0]["error_code"] == "browser.download_timeout"
    assert traces[1]["event_kind"] == "browser.download_failed"


def test_browser_wait_for_navigation_timeout_is_recorded_as_failed_network_trace() -> None:
    class FakePage:
        url = "https://example.test/items"

        def wait_for_timeout(self, delay_ms: int) -> None:
            return None

    recorder = NetworkTraceRecorder()
    context = _context(recorder=recorder, browser_runtime={"page": FakePage()})

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_navigation",
        {
            "node_id": "node-wait-navigation-timeout",
            "node_kind": "browser.wait_for_navigation",
            "node_config": {"url_pattern": "/missing", "timeout": 0},
        },
        context,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "browser.navigation_timeout"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert traces[0]["error_code"] == "browser.navigation_timeout"
    assert traces[1]["event_kind"] == "browser.navigation_failed"


def test_browser_wait_for_url_change_timeout_is_recorded_as_failed_network_trace() -> None:
    class FakePage:
        url = "https://example.test/items"

        def wait_for_timeout(self, delay_ms: int) -> None:
            return None

    recorder = NetworkTraceRecorder()
    context = _context(recorder=recorder, browser_runtime={"page": FakePage()})

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_url_change",
        {
            "node_id": "node-wait-url-change-timeout",
            "node_kind": "browser.wait_for_url_change",
            "node_config": {"from_url": "https://example.test/items", "timeout": 0},
        },
        context,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "browser.url_change_timeout"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert traces[0]["error_code"] == "browser.url_change_timeout"
    assert traces[1]["event_kind"] == "browser.url_change_failed"


def test_browser_wait_for_response_keeps_complete_body_in_debug_trace() -> None:
    recorder = NetworkTraceRecorder()
    context = _context(
        recorder=recorder,
        browser_runtime={
            "response_records": [
                {
                    "url": "https://example.test/items",
                    "status_code": 200,
                    "headers": {"content-type": "application/json"},
                    "body_text": '{"secret":"response-value"}',
                    "ok": True,
                }
            ]
        },
    )

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_response",
        {
            "node_id": "node-wait-response",
            "node_kind": "browser.wait_for_response",
            "node_config": {"url_pattern": "/items", "timeout": 1},
        },
        context,
    )

    assert result["status"] == "succeeded"
    trace = recorder.get_trace(
        recorder.list_traces(debug_session_id="debug-browser-listener")[0]["trace_id"]
    )
    assert trace["operation"]["response_status"] == 200
    assert trace["operation"]["response_body"]["value"] == '{"secret":"response-value"}'
    assert trace["messages"][0]["event_kind"] == "browser.response_observed"
    assert trace["messages"][0]["debug_event_index"] == 5


def test_browser_listener_spills_large_request_and_response_bodies_to_debug_resources(tmp_path) -> None:
    class FakePage:
        url = "https://example.test/items"

    request_body = "request-" + "x" * TRACE_MESSAGE_BODY_THRESHOLD_BYTES
    response_body = "response-" + "y" * TRACE_MESSAGE_BODY_THRESHOLD_BYTES
    recorder = NetworkTraceRecorder()
    network_service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    context = _context(
        recorder=recorder,
        browser_runtime={
            "page": FakePage(),
            "request_records": [
                {
                    "url": "https://example.test/items",
                    "method": "POST",
                    "headers": {"content-type": "text/plain"},
                    "post_data": request_body,
                }
            ],
            "response_records": [
                {
                    "url": "https://example.test/items",
                    "method": "POST",
                    "status_code": 200,
                    "headers": {"content-type": "text/plain"},
                    "body_text": response_body,
                }
            ],
        },
    )
    context.flow_runtime["network_runtime_service"] = network_service

    try:
        RuntimeExecutorRegistry().execute(
            "browser.wait_for_request",
            {
                "node_id": "node-large-browser-request",
                "node_kind": "browser.wait_for_request",
                "node_config": {"url_pattern": "/items", "timeout": 1},
            },
            context,
        )
        RuntimeExecutorRegistry().execute(
            "browser.wait_for_response",
            {
                "node_id": "node-large-browser-response",
                "node_kind": "browser.wait_for_response",
                "node_config": {"url_pattern": "/items", "timeout": 1},
            },
            context,
        )
        traces = recorder.list_traces(debug_session_id="debug-browser-listener")
        request_trace = next(item for item in traces if item.get("operation_id") == "node-large-browser-request" and "method" in item)
        response_trace = next(item for item in traces if item.get("operation_id") == "node-large-browser-response" and "method" in item)
        request_descriptor = request_trace["request_body"]
        response_descriptor = response_trace["response_body"]
        assert network_service.read_debug_body("debug-browser-listener", request_descriptor).decode() == request_body
        assert network_service.read_debug_body("debug-browser-listener", response_descriptor).decode() == response_body
    finally:
        network_service.close()

    assert "value" not in request_descriptor
    assert "value" not in response_descriptor


def test_browser_wait_for_popup_is_recorded_in_debug_network_trace(monkeypatch) -> None:
    class FakePage:
        url = "https://example.test/popup"

        def is_closed(self) -> bool:
            return False

    monkeypatch.setattr(engine_module, "Page", FakePage)
    popup_page = FakePage()
    recorder = NetworkTraceRecorder()
    context = _context(
        recorder=recorder,
        browser_runtime={
            "popup_records": [{"page": popup_page, "page_index": 1}],
            "pages": [popup_page],
            "page": popup_page,
            "page_labels": {},
        },
    )

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_popup",
        {
            "node_id": "node-wait-popup",
            "node_kind": "browser.wait_for_popup",
            "node_config": {"timeout": 1, "activate": False},
        },
        context,
    )

    assert result["status"] == "succeeded"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert len(traces) == 2
    assert traces[0]["protocol"] == "browser"
    assert traces[0]["url"] == "https://example.test/popup"
    assert traces[1]["event_kind"] == "browser.popup_observed"
    assert traces[1]["payload"]["page_url"] == "https://example.test/popup"
    assert "page" not in traces[1]["payload"]


def test_browser_wait_for_download_is_recorded_in_debug_network_trace(tmp_path) -> None:
    class FakeDownload:
        url = "https://example.test/export.csv"
        suggested_filename = "export.csv"

        def __init__(self) -> None:
            self.saved_path = None

        def save_as(self, path: str) -> None:
            self.saved_path = path

    download = FakeDownload()
    recorder = NetworkTraceRecorder()
    context = _context(
        recorder=recorder,
        browser_runtime={
            "download_records": [
                {
                    "download": download,
                    "url": download.url,
                    "suggested_filename": download.suggested_filename,
                    "page_index": 0,
                }
            ]
        },
    )
    context.runtime_settings["file_access_scope"] = "allow_all"
    registry = RuntimeExecutorRegistry(
        runtime_settings={
            "allow_browser_downloads": True,
        }
    )

    result = registry.execute(
        "browser.wait_for_download",
        {
            "node_id": "node-wait-download",
            "node_kind": "browser.wait_for_download",
            "node_config": {"path": str(tmp_path / "export.csv"), "timeout": 1},
        },
        context,
    )

    assert result["status"] == "succeeded"
    assert download.saved_path == str(tmp_path / "export.csv")
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert len(traces) == 2
    assert traces[0]["protocol"] == "browser"
    assert traces[0]["method"] == "DOWNLOAD"
    assert traces[0]["url"] == download.url
    assert traces[1]["event_kind"] == "browser.download_observed"
    assert traces[1]["payload"]["suggested_filename"] == "export.csv"
    assert "download" not in traces[1]["payload"]


def test_browser_wait_for_navigation_is_recorded_in_debug_network_trace() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.url = "https://example.test/start"

        def wait_for_timeout(self, delay_ms: int) -> None:
            self.url = "https://example.test/finish"

    page = FakePage()
    recorder = NetworkTraceRecorder()
    context = _context(recorder=recorder, browser_runtime={"page": page})

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_navigation",
        {
            "node_id": "node-wait-navigation",
            "node_kind": "browser.wait_for_navigation",
            "node_config": {"url_pattern": "/finish", "timeout": 100},
        },
        context,
    )

    assert result["status"] == "succeeded"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert traces[0]["method"] == "NAVIGATION"
    assert traces[0]["url"] == "https://example.test/finish"
    assert traces[1]["event_kind"] == "browser.navigation_observed"
    assert traces[1]["payload"]["matched_url"] == "https://example.test/finish"


def test_browser_wait_for_timeout_is_recorded_in_debug_network_trace() -> None:
    class FakePage:
        url = "https://example.test/wait"

        def wait_for_timeout(self, delay_ms: int) -> None:
            return None

    recorder = NetworkTraceRecorder()
    context = _context(recorder=recorder, browser_runtime={"page": FakePage()})

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_timeout",
        {
            "node_id": "node-wait-timeout",
            "node_kind": "browser.wait_for_timeout",
            "node_config": {"timeout": 50},
        },
        context,
    )

    assert result["status"] == "succeeded"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert traces[0]["method"] == "WAIT"
    assert traces[0]["url"] == "https://example.test/wait"
    assert traces[1]["event_kind"] == "browser.timeout_observed"
    assert traces[1]["payload"]["timeout_ms"] == 50


def test_browser_wait_for_url_change_is_recorded_in_debug_network_trace() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.url = "https://example.test/before"

        def wait_for_timeout(self, delay_ms: int) -> None:
            self.url = "https://example.test/after"

    page = FakePage()
    recorder = NetworkTraceRecorder()
    context = _context(recorder=recorder, browser_runtime={"page": page})

    result = RuntimeExecutorRegistry().execute(
        "browser.wait_for_url_change",
        {
            "node_id": "node-wait-url-change",
            "node_kind": "browser.wait_for_url_change",
            "node_config": {
                "from_url": "https://example.test/before",
                "url_pattern": "/after",
                "timeout": 100,
            },
        },
        context,
    )

    assert result["status"] == "succeeded"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    assert traces[0]["method"] == "NAVIGATION"
    assert traces[0]["url"] == "https://example.test/after"
    assert traces[1]["event_kind"] == "browser.url_change_observed"
    assert traces[1]["payload"]["from_url"] == "https://example.test/before"


def test_dialog_watch_and_handle_are_recorded_in_debug_network_trace() -> None:
    class FakePage:
        url = "https://example.test/dialog"

    dialog_record = {
        "type": "alert",
        "message": "dialog-message",
        "default_value": "",
        "action": "accept",
    }
    recorder = NetworkTraceRecorder()
    context = _context(
        recorder=recorder,
        browser_runtime={
            "page": FakePage(),
            "dialog_handler_installed": True,
            "dialog_records": [dialog_record],
        },
    )
    registry = RuntimeExecutorRegistry()

    watched = registry.execute(
        "dialog.watch_dialogs",
        {
            "node_id": "node-watch-dialogs",
            "node_kind": "dialog.watch_dialogs",
            "node_config": {"timeout": 0},
        },
        context,
    )
    handled = registry.execute(
        "dialog.handle_dialogs",
        {
            "node_id": "node-handle-dialogs",
            "node_kind": "dialog.handle_dialogs",
            "node_config": {"clear_after": False},
        },
        context,
    )

    assert watched["status"] == "succeeded"
    assert handled["status"] == "succeeded"
    traces = recorder.list_traces(debug_session_id="debug-browser-listener")
    events = [item["event_kind"] for item in traces if "event_kind" in item]
    assert events == ["browser.dialogs_watched", "browser.dialogs_handled"]
    assert traces[1]["payload"]["dialogs"] == [dialog_record]
    assert traces[3]["payload"]["handled_count"] == 1
