import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from socketserver import TCPServer

from weconduct.api.server import WeConductApiHandler


def test_http_compile_returns_failed_payload_for_empty_native_flow() -> None:
    class ApiTestServer(TCPServer):
        allow_reuse_address = True

    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = (
        Path(__file__).resolve().parents[2] / ".pytest_tmp" / "compile-errors-workspace-state.json"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        compile_payload = json.dumps(
            {
                "source_kind": "native_flow",
                "entry_document": "examples/empty.json",
                "source_text": '{"nodes":[]}',
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/workbench/compile",
            data=compile_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            categories = [
                entry["category"]
                for entry in payload["outcome"]["diagnostic_catalog"]["entries"]
            ]
            assert exc.code == 400
            assert payload["status"] == "failed"
            assert payload["view"]["status"] == "failed"
            assert payload["view"]["graph_stats"]["node_count"] == 0
            assert payload["view"]["diagnostic_summary"]["highest_severity"] == "fatal"
            assert payload["view"]["primary_diagnostic"]["category"] == "source.empty"
            assert payload["view"]["stage_overview"]["failed_stage_count"] == 1
            assert payload["view"]["stage_overview"]["terminal_stage"] == "validate"
            assert payload["view"]["stage_cards"][2]["stage"] == "validate"
            assert payload["view"]["stage_cards"][2]["status"] == "failed"
            assert payload["view"]["duration_ms"] is not None
            assert isinstance(payload["view"]["duration_ms"], int)
            assert payload["view"]["duration_ms"] >= 0
            assert payload["outcome"]["compilation_summary"]["duration_ms"] == payload["view"]["duration_ms"]
            assert "source.empty" in categories
            assert payload["outcome"]["compilation_summary"]["stage_outcomes"][2]["status"] == "failed"
        else:
            raise AssertionError("expected HTTPError for empty native flow")
    finally:
        server.shutdown()
        server.server_close()


def test_http_compile_rejects_invalid_json_payload() -> None:
    class ApiTestServer(TCPServer):
        allow_reuse_address = True

    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = (
        Path(__file__).resolve().parents[2] / ".pytest_tmp" / "compile-errors-workspace-state.json"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/workbench/compile",
            data=b"{not-json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload == {
                "error": "invalid_request",
                "message": "request body must be valid JSON",
            }
        else:
            raise AssertionError("expected HTTPError for invalid JSON payload")
    finally:
        server.shutdown()
        server.server_close()


def test_http_compile_rejects_missing_required_fields() -> None:
    class ApiTestServer(TCPServer):
        allow_reuse_address = True

    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = (
        Path(__file__).resolve().parents[2] / ".pytest_tmp" / "compile-errors-workspace-state.json"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        compile_payload = json.dumps(
            {
                "source_kind": "native_flow",
                "entry_document": "examples/missing-source-text.json",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/workbench/compile",
            data=compile_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload == {
                "error": "invalid_request",
                "message": "missing required field: source_text",
            }
        else:
            raise AssertionError("expected HTTPError for missing required field")
    finally:
        server.shutdown()
        server.server_close()


def test_http_compile_rejects_invalid_field_types() -> None:
    class ApiTestServer(TCPServer):
        allow_reuse_address = True

    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = (
        Path(__file__).resolve().parents[2] / ".pytest_tmp" / "compile-errors-workspace-state.json"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    invalid_cases = [
        (
            {
                "source_kind": None,
                "entry_document": "examples/native-flow.json",
                "source_text": '{"nodes":[]}',
            },
            "field must be a non-empty string: source_kind",
        ),
        (
            {
                "source_kind": "native_flow",
                "entry_document": 123,
                "source_text": '{"nodes":[]}',
            },
            "field must be a non-empty string: entry_document",
        ),
        (
            {
                "source_kind": "native_flow",
                "entry_document": "examples/native-flow.json",
                "source_text": [],
            },
            "field must be a string: source_text",
        ),
        (
            {
                "source_kind": "",
                "entry_document": "examples/native-flow.json",
                "source_text": '{"nodes":[]}',
            },
            "field must be a non-empty string: source_kind",
        ),
    ]

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        for compile_payload_data, expected_message in invalid_cases:
            compile_payload = json.dumps(compile_payload_data).encode("utf-8")
            request = urllib.request.Request(
                f"{base_url}/api/workbench/compile",
                data=compile_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            try:
                urllib.request.urlopen(request)
            except urllib.error.HTTPError as exc:
                payload = json.loads(exc.read().decode("utf-8"))
                assert exc.code == 400
                assert payload == {
                    "error": "invalid_request",
                    "message": expected_message,
                }
            else:
                raise AssertionError("expected HTTPError for invalid compile field types")
    finally:
        server.shutdown()
        server.server_close()


def test_http_compile_rejects_non_object_json_payload() -> None:
    class ApiTestServer(TCPServer):
        allow_reuse_address = True

    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = (
        Path(__file__).resolve().parents[2] / ".pytest_tmp" / "compile-errors-workspace-state.json"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/workbench/compile",
            data=b'["not-an-object"]',
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload == {
                "error": "invalid_request",
                "message": "request body must be a JSON object",
            }
        else:
            raise AssertionError("expected HTTPError for non-object JSON payload")
    finally:
        server.shutdown()
        server.server_close()


def test_http_compile_returns_failed_payload_for_invalid_native_flow_source_text() -> None:
    class ApiTestServer(TCPServer):
        allow_reuse_address = True

    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = (
        Path(__file__).resolve().parents[2] / ".pytest_tmp" / "compile-errors-workspace-state.json"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        compile_payload = json.dumps(
            {
                "source_kind": "native_flow",
                "entry_document": "examples/invalid-native-flow.json",
                "source_text": "{not-json",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/workbench/compile",
            data=compile_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            categories = [
                entry["category"]
                for entry in payload["outcome"]["diagnostic_catalog"]["entries"]
            ]
            assert exc.code == 400
            assert payload["status"] == "failed"
            assert payload["view"]["status"] == "failed"
            assert payload["view"]["stage_cards"][0]["stage"] == "parse"
            assert payload["view"]["stage_cards"][0]["status"] == "failed"
            assert payload["view"]["diagnostic_summary"]["highest_severity"] == "fatal"
            assert payload["view"]["primary_diagnostic"]["category"] == "source.parse_error"
            assert payload["view"]["stage_overview"]["failed_stage_count"] == 1
            assert payload["view"]["stage_overview"]["terminal_stage"] == "parse"
            assert payload["view"]["duration_ms"] is not None
            assert isinstance(payload["view"]["duration_ms"], int)
            assert payload["view"]["duration_ms"] >= 0
            assert payload["outcome"]["compilation_summary"]["duration_ms"] == payload["view"]["duration_ms"]
            assert "source.parse_error" in categories
        else:
            raise AssertionError("expected HTTPError for invalid native flow source text")
    finally:
        server.shutdown()
        server.server_close()
