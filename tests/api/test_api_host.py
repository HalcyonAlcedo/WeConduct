import json
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep
import urllib.error
import urllib.request
import pytest

from weconduct.api import build_api_server
from weconduct.application.compilation_workbench_service import CompilationWorkbenchService
from weconduct.api.server import ApiServerClosingError, WeConductApiHandler


def _build_mock_debug_session_response(
    *,
    session_id: str = "debug-session-mock",
    session_status: str = "paused",
    paused_reason: str | None = "breakpoint_hit",
) -> dict:
    return {
        "request": {},
        "debug_session": {
            "session_id": session_id,
            "status": session_status,
            "started_at": "2026-07-03T00:00:00+00:00",
            "paused_reason": paused_reason,
        },
        "stage_timeline": [],
        "object_index": {"graph_model_id": "graph:workspace"},
        "diagnostic_links": [],
        "runtime_preview": {"current_node": {"node_id": "node-start"}},
        "runtime_preview_summary": {"current_node_id": "node-start"},
        "variable_snapshot": {},
        "debug_events": [],
        "debug_keyframes": [],
    }


def test_build_api_server_applies_host_port_and_workspace_state_path(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    ui_dist_path = tmp_path / "ui-dist"

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        ui_dist_path=ui_dist_path,
    )
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_address[1] > 0
        assert server.workspace_state_path == workspace_state_path
        assert server.ui_dist_path == ui_dist_path
    finally:
        server.server_close()


def test_api_server_close_shuts_down_workbench_debug_sessions(tmp_path: Path) -> None:
    service = CompilationWorkbenchService()
    shutdown_calls: list[dict] = []

    def record_shutdown(*, reason: str = "application_shutdown", timeout_seconds: float = 5.0) -> None:
        shutdown_calls.append({"reason": reason, "timeout_seconds": timeout_seconds})

    service.shutdown_debug_sessions = record_shutdown  # type: ignore[method-assign]
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        ui_dist_path=tmp_path / "ui-dist",
    )
    server.workbench_service = service

    server.server_close()

    assert shutdown_calls == [
        {
            "reason": "application_shutdown",
            "timeout_seconds": 5.0,
        }
    ]


def test_build_api_server_migrates_program_configuration_before_serving(
    tmp_path: Path,
) -> None:
    preferences_path = tmp_path / "runtime" / "preferences.json"
    preferences_path.parent.mkdir(parents=True)
    preferences_path.write_text(
        json.dumps(
            {
                "preferences_file_version": 2,
                "program_settings": {
                    "default_window_size": {"width": 1500, "height": 920}
                },
            }
        ),
        encoding="utf-8",
    )

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=preferences_path,
        ui_dist_path=tmp_path / "ui-dist",
    )
    try:
        migrated = json.loads(preferences_path.read_text(encoding="utf-8"))
        assert migrated["configuration_format_version"] == 1
        assert migrated["scope"] == "program"
        assert migrated["values"]["ui"]["default_window_size"] == {
            "width": 1500,
            "height": 920,
        }
    finally:
        server.server_close()


def test_api_server_close_waits_for_inflight_debug_action_and_rejects_new_action(
    tmp_path: Path,
) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        ui_dist_path=tmp_path / "ui-dist",
    )
    action_started = Event()
    release_action = Event()
    close_finished = Event()

    def inflight_action() -> dict:
        action_started.set()
        assert release_action.wait(timeout=1.0), "inflight debug action was not released"
        return {"status": "started"}

    action_thread = Thread(
        target=lambda: server.execute_debug_action(inflight_action),
        daemon=True,
    )
    action_thread.start()
    assert action_started.wait(timeout=1.0)

    close_thread = Thread(
        target=lambda: (server.server_close(), close_finished.set()),
        daemon=True,
    )
    close_thread.start()
    sleep(0.05)
    assert close_finished.is_set() is False
    release_action.set()
    action_thread.join(timeout=1.0)
    close_thread.join(timeout=1.0)

    assert close_finished.is_set() is True
    with pytest.raises(ApiServerClosingError):
        server.execute_debug_action(lambda: {"status": "started"})


def test_compile_failure_payload_contains_only_compile_error_fields() -> None:
    handler = WeConductApiHandler.__new__(WeConductApiHandler)

    payload = handler._build_compile_failure_error_payload(
        {
            "view": {
                "primary_diagnostic": {
                    "message": "source document is invalid",
                    "category": "compile.invalid_source",
                },
                "diagnostic_summary": {
                    "total_count": 1,
                    "highest_severity": "error",
                },
                "stage_overview": {
                    "current_stage": "validate_source",
                },
            },
            "runtime_session": {"session_id": "runtime-1"},
            "runtime_plan": {"steps": ["prepare"]},
            "node_states": [{"node_id": "node-1"}],
            "event_log": [{"event_kind": "runtime.started"}],
            "diagnostics": {"total_count": 99},
            "result": {"failure_reason": "should-not-leak"},
        },
        error_code="compile_failed",
    )

    assert payload == {
        "error": "compile_failed",
        "message": "source document is invalid",
        "details": {
            "primary_diagnostic": {
                "message": "source document is invalid",
                "category": "compile.invalid_source",
            },
            "diagnostic_summary": {
                "total_count": 1,
                "highest_severity": "error",
            },
            "stage_overview": {
                "current_stage": "validate_source",
            },
        },
    }


def test_api_exposes_debug_continue_action(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-api-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {
                                    "username": "original-user",
                                    "retry_count": 0,
                                },
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        response_payload = _post_json(
            f"{base_url}/api/workbench/debug/{session_id}/continue",
            {},
        )

        assert response_payload["debug_session"]["status"] == "completed"
        assert response_payload["debug_session"]["session_id"] == session_id
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_debug_start_auto_runs_to_initial_pause(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        payload = _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )

        assert payload["debug_session"]["status"] == "paused"
        assert payload["debug_session"]["paused_reason"] == "breakpoint_hit"
        assert payload["runtime_preview"]["current_node"]["node_id"] == "node-start"

        update_payload = _post_json(
            f"{base_url}/api/workbench/debug/{payload['debug_session']['session_id']}/debugger-config/apply",
            {
                "node_id": "node-start",
                "debugger": {
                    "breakpoint": {"enabled": False, "pause_timing": "before"},
                    "record_frame": {"enabled": True},
                },
            },
        )

        assert update_payload["status"] == "updated"
        assert update_payload["node_id"] == "node-start"
        assert update_payload["debugger"]["breakpoint"]["enabled"] is False
        assert update_payload["debugger"]["record_frame"]["enabled"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_exposes_debug_history_list_and_open(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-history-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        history_payload = _get_json(f"{base_url}/api/workbench/debug/history")
        session_id = history_payload["sessions"][0]["session_id"]

        open_payload = _get_json(f"{base_url}/api/workbench/debug/history/{session_id}")

        assert history_payload["summary"]["debug_session_count"] >= 1
        assert history_payload["sessions"][0]["session_id"] == session_id
        assert open_payload["session_id"] == session_id
        assert open_payload["source"] == "history_store"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_prepare_debug_session_is_pure_precheck_and_not_openable_before_start(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {
                "project_name": "debug-prepare-precheck-test",
                "project_directory": str(tmp_path / "project"),
            },
        )
        history_before = _get_json(f"{base_url}/api/workbench/debug/history")["sessions"]
        history_session_ids_before = [item["session_id"] for item in history_before]
        prepare_payload = _post_json(
            f"{base_url}/api/workbench/debug/prepare",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        assert prepare_payload["status"] == "ready"
        assert "debug_session" not in prepare_payload
        assert _get_json(f"{base_url}/api/workbench/debug/sessions")["sessions"] == []
        history_after = _get_json(f"{base_url}/api/workbench/debug/history")["sessions"]
        assert [item["session_id"] for item in history_after] == history_session_ids_before

        session_id = "debug-session-from-prepare"
        request = urllib.request.Request(
            f"{base_url}/api/workbench/debug/{session_id}/continue",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        body = json.loads(exc_info.value.read().decode("utf-8"))

        assert exc_info.value.code == 400
        assert body["error"] == "invalid_request"
        assert body["message"] == f"debug session not found: {session_id}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_prepare_runtime_session_is_pure_precheck_and_does_not_open_session(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        prepare_payload = _post_json(
            f"{base_url}/api/workbench/runtime/prepare",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )

        assert prepare_payload["status"] == "ready"
        assert "runtime_session" not in prepare_payload
        assert _get_json(f"{base_url}/api/workbench/runtime/sessions")["sessions"] == []
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_exposes_runtime_abort_action(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        ui_dist_path=ui_dist_path,
    )
    server.workbench_service = CompilationWorkbenchService()
    calls: list[dict] = []

    def abort_runtime_session(*, session_id: str, reason: str) -> dict:
        calls.append({"session_id": session_id, "reason": reason})
        return {
            "status": "aborted",
            "runtime_session": {
                "session_id": session_id,
                "status": "aborted",
                "abort_reason": reason,
                "aborted_at": "2026-07-11T00:00:00+00:00",
            },
        }

    server.workbench_service.abort_runtime_session = abort_runtime_session  # type: ignore[method-assign]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        payload = _post_json(
            f"{base_url}/api/workbench/runtime/runtime-session-1/abort",
            {"reason": "user_abort"},
        )

        assert payload["status"] == "aborted"
        assert payload["runtime_session"]["status"] == "aborted"
        assert calls == [
            {"session_id": "runtime-session-1", "reason": "user_abort"}
        ]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_exposes_runtime_pending_input_and_parameter_unlock_actions(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        ui_dist_path=ui_dist_path,
    )
    server.workbench_service = CompilationWorkbenchService()
    submitted: list[dict] = []
    unlocked: list[dict] = []

    def get_pending_input_snapshot(*, execution_id: str) -> dict:
        return {
            "execution_id": execution_id,
            "request_id": "input-1",
            "status": "waiting",
            "fields": [{"field_id": "password", "label": "Password", "sensitive": True}],
            "timeout_seconds": 0,
        }

    def submit_pending_input(*, execution_id: str, request_id: str, values: dict) -> dict:
        submitted.append({"execution_id": execution_id, "request_id": request_id, "values": values})
        return {"execution_id": execution_id, "request_id": request_id, "status": "submitted"}

    def unlock_runtime_session_parameters(*, session_id: str, password: str) -> dict:
        unlocked.append({"session_id": session_id, "password": password})
        return {"status": "unlocked", "parameter_ids": ["api_key"]}

    server.workbench_service.get_pending_input_snapshot = get_pending_input_snapshot  # type: ignore[method-assign]
    server.workbench_service.submit_pending_input = submit_pending_input  # type: ignore[method-assign]
    server.workbench_service.unlock_runtime_session_parameters = unlock_runtime_session_parameters  # type: ignore[method-assign]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        pending = _get_json(f"{base_url}/api/workbench/runtime/runtime-session-1/pending-input")
        submitted_snapshot = _post_json(
            f"{base_url}/api/workbench/runtime/runtime-session-1/pending-input",
            {"request_id": "input-1", "values": {"password": "private-value"}},
        )
        unlock_result = _post_json(
            f"{base_url}/api/workbench/runtime/runtime-session-1/unlock",
            {"password": "unlock-value"},
        )

        assert pending["status"] == "waiting"
        assert submitted_snapshot["status"] == "submitted"
        assert unlock_result == {"status": "unlocked", "parameter_ids": ["api_key"]}
        assert submitted == [{"execution_id": "runtime-session-1", "request_id": "input-1", "values": {"password": "private-value"}}]
        assert unlocked == [{"session_id": "runtime-session-1", "password": "unlock-value"}]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_runtime_start_failure_retains_runtime_payload(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps(
                {
                    "graph_document": {
                        "graph_model_id": "graph:workspace",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        body = json.loads(exc_info.value.read().decode("utf-8"))

        assert exc_info.value.code == 400
        assert body["error"] == "runtime_start_failed"
        assert "runtime_session" in body
        assert "diagnostics" in body
        assert "node_states" in body
        assert "event_log" in body
        assert "result" in body
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_runtime_start_conflict_failure_exposes_diagnostic_summary(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "runtime-conflict-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )

        request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        body = json.loads(exc_info.value.read().decode("utf-8"))

        assert exc_info.value.code == 400
        assert body["error"] == "runtime_start_failed"
        assert body["diagnostics"]["total_count"] == 1
        assert body["diagnostics"]["highest_severity"] == "error"
        assert body["details"]["diagnostic_summary"]["total_count"] == 1
        assert body["details"]["primary_diagnostic"]["category"] == "debug.session_conflict"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_exposes_debug_projection_live_and_history(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-projection-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        _post_json(
            f"{base_url}/api/workbench/debug/{session_id}/variables/apply",
            {"updates": {"username": "first"}, "apply_mode": "immediate"},
        )
        first_event_index = _get_json(
            f"{base_url}/api/workbench/debug/{session_id}/events"
        )["events"][-1]["event_index"]
        _post_json(
            f"{base_url}/api/workbench/debug/{session_id}/variables/apply",
            {"updates": {"username": "second"}, "apply_mode": "immediate"},
        )
        second_event_index = _get_json(
            f"{base_url}/api/workbench/debug/{session_id}/events"
        )["events"][-1]["event_index"]

        live_payload = _get_json(f"{base_url}/api/workbench/debug/projection/live/{session_id}")
        history_payload = _get_json(f"{base_url}/api/workbench/debug/projection/history/{session_id}")
        first_history_payload = _get_json(
            f"{base_url}/api/workbench/debug/projection/history/{session_id}"
            f"?event_index={first_event_index}"
        )
        second_history_payload = _get_json(
            f"{base_url}/api/workbench/debug/projection/history/{session_id}"
            f"?event_index={second_event_index}"
        )
        history_session = _get_json(
            f"{base_url}/api/workbench/debug/history/{session_id}"
        )["session"]
        keyframe_id = history_session["keyframes"][-1]["keyframe_id"]
        keyframe_history_payload = _get_json(
            f"{base_url}/api/workbench/debug/projection/history/{session_id}"
            f"?keyframe_id={keyframe_id}"
        )

        assert live_payload["session_id"] == session_id
        assert live_payload["projection"]["mode"] == "live"
        assert history_payload["session_id"] == session_id
        assert history_payload["projection"]["mode"] == "history"
        assert history_payload["source"] == "history_store"
        assert first_history_payload["variable_snapshot"]["username"] == "first"
        assert second_history_payload["variable_snapshot"]["username"] == "second"
        assert keyframe_history_payload["projection"]["history_keyframe_id"] == keyframe_id
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_exposes_debug_event_list(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-event-list-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        events_payload = _get_json(f"{base_url}/api/workbench/debug/{session_id}/events")

        assert events_payload["session_id"] == session_id
        assert events_payload["source"] == "history_store"
        assert events_payload["total_count"] >= 2
        assert events_payload["events"][0]["event_kind"] == "breakpoint.hit"
        assert events_payload["events"][0]["event_index"] == 0
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_does_not_expose_debug_record_frame_event_injection(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-record-frame-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        request = urllib.request.Request(
            f"{base_url}/api/workbench/debug/{session_id}/record-frame",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 404
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_does_not_expose_context_free_debug_record_frame_event_injection(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-record-frame-auto-context-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        request = urllib.request.Request(
            f"{base_url}/api/workbench/debug/{session_id}/record-frame",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 404
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_rejects_pause_for_already_paused_session(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-pause-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        with pytest.raises(
            AssertionError,
            match="debug pause is not allowed for session status: paused",
        ):
            _post_json(
                f"{base_url}/api/workbench/debug/{session_id}/pause",
                {
                    "node_id": "node-start",
                    "reason": "breakpoint_hit",
                },
            )

        events_payload = _get_json(f"{base_url}/api/workbench/debug/{session_id}/events")
        assert events_payload["events"][-1]["event_kind"] == "debug.paused"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_rejects_pause_without_node_id_for_already_paused_session(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-pause-auto-context-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        with pytest.raises(
            AssertionError,
            match="debug pause is not allowed for session status: paused",
        ):
            _post_json(
                f"{base_url}/api/workbench/debug/{session_id}/pause",
                {
                    "reason": "manual_pause",
                },
            )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_exposes_debug_continue_resumed_event(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-resume-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        continue_payload = _post_json(
            f"{base_url}/api/workbench/debug/{session_id}/continue",
            {},
        )

        assert continue_payload["status"] in {"accepted", "completed"}
        assert continue_payload["debug_session"]["status"] in {"running", "completed"}

        completed_payload = _wait_for_debug_session_status(
            base_url,
            session_id,
            expected_statuses={"completed"},
        )
        assert completed_payload["debug_session"]["status"] == "completed"

        events_payload = _get_json(f"{base_url}/api/workbench/debug/{session_id}/events")
        assert any(item["event_kind"] == "debug.resumed" for item in events_payload["events"])
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_exposes_debug_abort_action(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-abort-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        abort_payload = _post_json(
            f"{base_url}/api/workbench/debug/{session_id}/abort",
            {
                "reason": "user_abort",
            },
        )

        assert abort_payload["debug_session"]["session_id"] == session_id
        assert abort_payload["debug_session"]["status"] == "aborted"
        assert abort_payload["debug_session"]["last_control_action"] == "abort"

        events_payload = _get_json(f"{base_url}/api/workbench/debug/{session_id}/events")
        assert events_payload["events"][-1]["event_kind"] == "debug.aborted"
        assert events_payload["events"][-1]["reason"] == "user_abort"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_rejects_followup_debug_actions_after_abort(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-abort-guard-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        _post_json(
            f"{base_url}/api/workbench/debug/{session_id}/abort",
            {"reason": "user_abort"},
        )

        with pytest.raises(AssertionError, match="HTTP 400"):
            _post_json(f"{base_url}/api/workbench/debug/{session_id}/continue", {})

        with pytest.raises(AssertionError, match="HTTP 400"):
            _post_json(f"{base_url}/api/workbench/debug/{session_id}/abort", {"reason": "user_abort"})

        with pytest.raises(AssertionError, match="HTTP 400"):
            _post_json(f"{base_url}/api/workbench/debug/{session_id}/step-over", {})

        with pytest.raises(AssertionError, match="HTTP 400"):
            _post_json(f"{base_url}/api/workbench/debug/{session_id}/step-into", {})

        with pytest.raises(AssertionError, match="HTTP 400"):
            _post_json(f"{base_url}/api/workbench/debug/{session_id}/step-out", {})
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_exposes_debug_variable_apply_action(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-variable-apply-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {
                                    "username": "original-user",
                                    "retry_count": 0,
                                },
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        apply_payload = _post_json(
            f"{base_url}/api/workbench/debug/{session_id}/variables/apply",
            {
                "updates": {
                    "username": "debug-user",
                    "retry_count": 3,
                },
                "apply_mode": "staged",
            },
        )

        assert apply_payload["debug_session"]["session_id"] == session_id
        assert apply_payload["variable_snapshot"]["username"] == "original-user"
        assert apply_payload["variable_snapshot"]["retry_count"] == 0
        assert apply_payload["debug_session"]["pending_variable_overrides"] == {
            "username": "debug-user",
            "retry_count": 3,
        }
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_debug_start_route_uses_async_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_sync_start(
        self: CompilationWorkbenchService,
        graph_document_payload: dict | None,
    ) -> dict:
        raise AssertionError("sync debug start should not be called by API route")

    def fake_async_start(
        self: CompilationWorkbenchService,
        graph_document_payload: dict | None,
        *,
        settle_timeout_ms: int = 75,
    ) -> dict:
        assert settle_timeout_ms == 75
        return {"status": "started", **_build_mock_debug_session_response()}

    monkeypatch.setattr(CompilationWorkbenchService, "start_debug_session", fail_sync_start)
    monkeypatch.setattr(CompilationWorkbenchService, "start_debug_session_async", fake_async_start)

    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        payload = _post_json(f"{base_url}/api/workbench/debug/start", {})

        assert payload["debug_session"]["session_id"] == "debug-session-mock"
        assert payload["debug_session"]["status"] == "paused"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_debug_start_route_accepts_paused_async_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_async_start(
        self: CompilationWorkbenchService,
        graph_document_payload: dict | None,
        *,
        settle_timeout_ms: int = 75,
    ) -> dict:
        assert settle_timeout_ms == 75
        return {
            "status": "paused",
            **_build_mock_debug_session_response(),
        }

    monkeypatch.setattr(CompilationWorkbenchService, "start_debug_session_async", fake_async_start)

    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/workbench/debug/start",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "paused"
        assert payload["debug_session"]["session_id"] == "debug-session-mock"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_debug_continue_route_accepts_async_service_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_sync_continue(
        self: CompilationWorkbenchService,
        *,
        session_id: str,
    ) -> dict:
        raise AssertionError("sync debug continue should not be called by API route")

    def fake_async_continue(
        self: CompilationWorkbenchService,
        *,
        session_id: str,
        settle_timeout_ms: int = 500,
    ) -> dict:
        assert session_id == "debug-session-mock"
        assert settle_timeout_ms == 500
        return {"status": "accepted", "debug_session": {"session_id": session_id, "status": "running"}}

    monkeypatch.setattr(CompilationWorkbenchService, "continue_debug_session", fail_sync_continue)
    monkeypatch.setattr(CompilationWorkbenchService, "continue_debug_session_async", fake_async_continue)

    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        payload = _post_json(f"{base_url}/api/workbench/debug/debug-session-mock/continue", {})

        assert payload["status"] == "accepted"
        assert payload["debug_session"]["status"] == "running"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_debug_pause_route_uses_pause_request_and_accepts_pending_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request_pause(
        self: CompilationWorkbenchService,
        *,
        session_id: str,
        node_id: str | None,
        reason: str,
    ) -> dict:
        assert session_id == "debug-session-mock"
        assert node_id == "node-start"
        assert reason == "manual_pause"
        return {
            "status": "accepted",
            "event": {
                "event_kind": "debug.pause_requested",
                "node_id": node_id,
                "reason": reason,
            },
            "debug_session": {
                "session_id": session_id,
                "status": "running",
            },
        }

    monkeypatch.setattr(CompilationWorkbenchService, "request_debug_pause", fake_request_pause)

    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        payload = _post_json(
            f"{base_url}/api/workbench/debug/debug-session-mock/pause",
            {"node_id": "node-start", "reason": "manual_pause"},
        )

        assert payload["status"] == "accepted"
        assert payload["event"]["event_kind"] == "debug.pause_requested"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize(
    ("route_suffix", "expected_step_mode"),
    [
        ("step-over", "step_over"),
        ("step-into", "step_into"),
    ],
)
def test_api_exposes_debug_step_actions(
    tmp_path: Path,
    route_suffix: str,
    expected_step_mode: str,
) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-step-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {"username": "original-user"},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        },
                        {
                            "node_id": "node-next",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n-node-next",
                            "expansion_role": "data.set_variable",
                            "display_name": "写入变量",
                            "node_kind": "data.set_variable",
                            "position": {"x": 180, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-in",
                                    "direction": "input",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.previous",
                                }
                            ],
                            "node_config": {
                                "name": "username",
                                "value": "debug-user",
                            },
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge-start-next",
                            "from_node_id": "node-start",
                            "from_port_id": "control-out",
                            "to_node_id": "node-next",
                            "to_port_id": "control-in",
                            "relation_layer": "control",
                        }
                    ],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        step_payload = _post_json(
            f"{base_url}/api/workbench/debug/{session_id}/{route_suffix}",
            {},
        )

        assert step_payload["status"] in {"accepted", "paused"}
        assert step_payload["debug_session"]["session_id"] == session_id
        assert step_payload["debug_session"]["status"] in {"running", "stepping", "paused"}

        paused_payload = _wait_for_debug_session_status(
            base_url,
            session_id,
            expected_statuses={"paused"},
        )
        assert paused_payload["debug_session"]["step_mode"] == expected_step_mode
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_rejects_top_level_debug_step_out(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(
            f"{base_url}/api/workbench/project/new",
            {"project_name": "debug-step-out-test", "project_directory": str(tmp_path / "project")},
        )
        _post_json(
            f"{base_url}/api/workbench/debug/start",
            {
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "position": {"x": 0, "y": 0},
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                            "node_config": {
                                "initial_variables": {},
                                "browser_config": {"headless": True},
                                "execution_defaults": {
                                    "default_timeout_ms": 30000,
                                    "default_retry_count": 0,
                                },
                                "debugger": {
                                    "breakpoint": {
                                        "enabled": True,
                                        "pause_timing": "before",
                                    }
                                },
                            },
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            },
        )
        sessions_payload = _get_json(f"{base_url}/api/workbench/debug/sessions")
        session_id = sessions_payload["sessions"][0]["session_id"]

        with pytest.raises(
            AssertionError,
            match="HTTP 400.*debug step_out is only available inside a component",
        ):
            _post_json(f"{base_url}/api/workbench/debug/{session_id}/step-out", {})
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize(
    ("route_suffix", "sync_method_name", "async_method_name", "expected_step_mode"),
    [
        ("step-over", "step_over_debug_session", "step_over_debug_session_async", "step_over"),
        ("step-into", "step_into_debug_session", "step_into_debug_session_async", "step_into"),
        ("step-out", "step_out_debug_session", "step_out_debug_session_async", "step_out"),
    ],
)
def test_api_debug_step_routes_use_async_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    route_suffix: str,
    sync_method_name: str,
    async_method_name: str,
    expected_step_mode: str,
) -> None:
    def fail_sync(self: CompilationWorkbenchService, *, session_id: str) -> dict:
        raise AssertionError(f"sync {sync_method_name} should not be called by API route")

    def fake_async(
        self: CompilationWorkbenchService,
        *,
        session_id: str,
        settle_timeout_ms: int = 75,
    ) -> dict:
        assert session_id == "debug-session-mock"
        assert settle_timeout_ms == 75
        return {
            "status": "accepted",
            "debug_session": {
                "session_id": session_id,
                "status": "stepping",
                "step_mode": expected_step_mode,
            },
        }

    monkeypatch.setattr(CompilationWorkbenchService, sync_method_name, fail_sync)
    monkeypatch.setattr(CompilationWorkbenchService, async_method_name, fake_async)

    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        payload = _post_json(
            f"{base_url}/api/workbench/debug/debug-session-mock/{route_suffix}",
            {},
        )

        assert payload["status"] == "accepted"
        assert payload["debug_session"]["step_mode"] == expected_step_mode
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_debug_abort_route_accepts_pending_abort_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_abort(
        self: CompilationWorkbenchService,
        *,
        session_id: str,
        reason: str,
    ) -> dict:
        assert session_id == "debug-session-mock"
        assert reason == "user_abort"
        return {
            "status": "accepted",
            "debug_session": {
                "session_id": session_id,
                "status": "running",
            },
        }

    monkeypatch.setattr(CompilationWorkbenchService, "abort_debug_session", fake_abort)

    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        payload = _post_json(
            f"{base_url}/api/workbench/debug/debug-session-mock/abort",
            {"reason": "user_abort"},
        )

        assert payload["status"] == "accepted"
        assert payload["debug_session"]["session_id"] == "debug-session-mock"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def test_api_exposes_program_configuration_schema_and_patch(tmp_path: Path) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

        schema = _get_json(f"{base_url}/api/workbench/config/schema?scope=program")
        updated = _patch_json(
            f"{base_url}/api/workbench/config/values",
            {
                "scope": "program",
                "operations": [
                    {
                        "op": "replace",
                        "path": "/updates/check_updates_on_startup",
                        "value": True,
                    }
                ],
            },
        )

        assert schema["scope"] == "program"
        assert any(domain["key"] == "security" for domain in schema["domains"])
        assert updated["values"]["updates"]["check_updates_on_startup"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_exposes_graph_configuration_scope(tmp_path: Path) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        created = _post_json(
            f"{base_url}/api/workbench/project/new",
            {
                "project_name": "graph-config",
                "project_directory": str(tmp_path / "project"),
            },
        )
        graph_document = created["graph_document"]
        graph_document["nodes"] = [
            {
                "node_id": "node-start",
                "lowered_kind": "control",
                "source_anchor_ref": "n-node-start",
                "expansion_role": "flow.start",
                "display_name": "流程入口",
                "node_kind": "flow.start",
                "position": {"x": 0, "y": 0},
                "ports": [],
                "node_config": {
                    "initial_variables": {},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                },
            }
        ]
        _put_json(f"{base_url}/api/workbench/graph", graph_document)
        updated = _patch_json(
            f"{base_url}/api/workbench/config/values",
            {
                "scope": "graph",
                "operations": [
                    {
                        "op": "replace",
                        "path": "/editor_preferences/save_conflict_policy",
                        "value": "strict",
                    },
                    {
                        "op": "replace",
                        "path": "/entrypoint_runtime/initial_variables",
                        "value": {"username": "configured"},
                    },
                    {
                        "op": "replace",
                        "path": "/entrypoint_runtime/browser_config",
                        "value": {"headless": False, "slow_mo_ms": 25},
                    },
                ],
            },
        )
        graph_document = _get_json(f"{base_url}/api/workbench/graph")
        flow_start = next(
            node
            for node in graph_document["graph_model"]["nodes"]
            if node["node_kind"] == "flow.start"
        )

        assert updated["values"]["editor_preferences"]["save_conflict_policy"] == "strict"
        assert flow_start["node_config"]["initial_variables"] == {"username": "configured"}
        assert flow_start["node_config"]["browser_config"] == {
            "headless": False,
            "slow_mo_ms": 25,
        }
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_api_exposes_project_configuration_scope(tmp_path: Path) -> None:
    server = build_api_server(host="127.0.0.1", port=0, workspace_state_path=tmp_path / "runtime" / "workspace-state.json", preferences_path=tmp_path / "runtime" / "preferences.json", ui_dist_path=tmp_path / "ui-dist")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _post_json(f"{base_url}/api/workbench/project/new", {"project_name": "before", "project_directory": str(tmp_path / "project")})
        updated = _patch_json(
            f"{base_url}/api/workbench/config/values",
            {
                "scope": "project",
                "operations": [
                    {"op": "replace", "path": "/identity/name", "value": "after"},
                    {"op": "replace", "path": "/debug/history_retention_limit", "value": 15},
                    {"op": "replace", "path": "/resources/embedded_resources", "value": ["input/a.txt"]},
                    {"op": "replace", "path": "/packaging/default_output_name", "value": "after.wcrun"},
                    {"op": "replace", "path": "/python_profile/runtime_enabled", "value": True},
                ],
            },
        )
        assert updated["values"]["identity"]["name"] == "after"
        assert updated["values"]["debug"]["history_retention_limit"] == 15
        assert updated["values"]["resources"]["embedded_resources"] == ["input/a.txt"]
        assert updated["values"]["packaging"]["default_output_name"] == "after.wcrun"
        assert updated["values"]["python_profile"]["runtime_enabled"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize(
    "route",
    [
        "/api/workbench/project/settings",
        "/api/workbench/project/runtime-defaults",
    ],
)
def test_api_does_not_expose_legacy_project_configuration_routes(
    tmp_path: Path,
    route: str,
) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"{base_url}{route}")
        assert error.value.code == 404
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _wait_for_debug_session_status(
    base_url: str,
    session_id: str,
    *,
    expected_statuses: set[str],
    timeout_seconds: float = 5.0,
) -> dict:
    deadline = monotonic() + timeout_seconds
    last_payload: dict | None = None
    while monotonic() < deadline:
        last_payload = _get_json(f"{base_url}/api/workbench/debug/{session_id}")
        status = last_payload.get("debug_session", {}).get("status")
        if status in expected_statuses:
            return last_payload
        sleep(0.05)
    raise AssertionError(
        f"debug session {session_id} did not reach {sorted(expected_statuses)}; "
        f"last payload: {last_payload}"
    )


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - keep response body visible in test failure
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"HTTP {exc.code} for {url}: {body}") from exc


def _patch_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - keep response body visible in test failure
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"HTTP {exc.code} for {url}: {body}") from exc


def _put_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - keep response body visible in test failure
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"HTTP {exc.code} for {url}: {body}") from exc
