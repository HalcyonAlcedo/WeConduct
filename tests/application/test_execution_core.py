from __future__ import annotations

from pathlib import Path

import pytest

from weconduct.application.execution_core import ExecutionCore
from weconduct.runtime.engine import (
    CancellationContext,
    RuntimeCancellationError,
    RuntimeContext,
    RuntimeExecutorRegistry,
)
from weconduct.runtime.execution_context import ExecutionTokenContext


class _Owner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _inject_runtime_data_edge_inputs(self, **_: object) -> None:
        self.calls.append("inject")

    def _execute_runtime_plan_node(self, **_: object) -> dict:
        self.calls.append("execute")
        return {"status": "completed", "value": 1}

    def _build_runtime_executor_exception_output(self, **_: object) -> dict:
        self.calls.append("exception")
        return {"status": "failed", "error_code": "runtime.exception"}


class _CancelledOwner(_Owner):
    def _execute_runtime_plan_node(self, **_: object) -> dict:
        raise AssertionError("execute should not run after cancellation")


class _FakePage:
    def __init__(self, cancellation_context: object) -> None:
        self.url = "https://example.test"
        self._cancellation_context = cancellation_context
        self.wait_calls: list[int] = []

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self.wait_calls.append(timeout_ms)
        if len(self.wait_calls) == 1:
            self._cancellation_context.request_cancel("stop wait")


class _FakeClosable:
    def __init__(self, name: str, log: list[str], *, error: Exception | None = None) -> None:
        self._name = name
        self._log = log
        self._error = error
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        self._log.append(self._name)
        if self._error is not None:
            raise self._error


class _FakePlaywright:
    def __init__(self, log: list[str], *, error: Exception | None = None) -> None:
        self._log = log
        self._error = error
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1
        self._log.append("playwright")
        if self._error is not None:
            raise self._error


class _FakePopen:
    def __init__(self, cancellation_context: object) -> None:
        self._cancellation_context = cancellation_context
        self.returncode: int | None = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.communicate_calls = 0

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self.communicate_calls += 1
        if self.communicate_calls == 1:
            self._cancellation_context.request_cancel("stop process")
            raise TimeoutError()
        self.returncode = -15
        return ("", "")

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = -15

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode if self.returncode is not None else -15


class _FakeHttpHeaders:
    def items(self) -> list[tuple[str, str]]:
        return [("content-type", "text/plain; charset=utf-8")]


class _FakeHttpResponse:
    def __init__(self, cancellation_context: object) -> None:
        self.status = 200
        self.headers = _FakeHttpHeaders()
        self._cancellation_context = cancellation_context
        self.close_calls = 0
        self.read_calls = 0

    def read(self, _: int = -1) -> bytes:
        self.read_calls += 1
        if self.read_calls == 1:
            self._cancellation_context.request_cancel("stop http")
            return b"part-1"
        return b""

    def close(self) -> None:
        self.close_calls += 1

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


class _FakeStreamingResponse(_FakeHttpResponse):
    pass


def test_execution_core_dispatches_token_with_iteration_identity() -> None:
    event_log: list[dict] = []
    cursor = ExecutionCore.dispatch_next_token(
        pending_node_entries=[
            {"node_index": 1, "repeat_mode": True, "iteration_stack": ["loop:2"]}
        ],
        executable_nodes=[
            {"node_id": "node-a", "node_kind": "data.set_variable"},
            {"node_id": "node-b", "node_kind": "control.while"},
        ],
        event_log=event_log,
        session_id="runtime-1",
    )

    assert cursor.program_counter == 1
    assert cursor.repeat_mode is True
    assert cursor.iteration_stack == ["loop:2"]
    assert [event["event_kind"] for event in event_log] == ["token.dispatched", "node.ready"]


def test_execution_core_dispatches_token_with_network_context_reference() -> None:
    cursor = ExecutionCore.dispatch_next_token(
        pending_node_entries=[
            {
                "node_index": 0,
                "repeat_mode": False,
                "iteration_stack": [],
                "token_context": {
                    "network_context_id": "network-context-1",
                    "network_context_epoch": 2,
                },
            }
        ],
        executable_nodes=[{"node_id": "node-a", "node_kind": "network.http_request"}],
    )

    assert cursor.token_context == ExecutionTokenContext(
        network_context_id="network-context-1",
        network_context_epoch=2,
    )


def test_execution_core_executes_injection_and_node_through_one_path() -> None:
    owner = _Owner()

    result = ExecutionCore.execute_node(
        owner=owner,
        executable_node={"node_id": "node-a"},
        runtime_context=object(),
        data_edges_by_target={},
        executor_registry=object(),
    )

    assert result == {"status": "completed", "value": 1}
    assert owner.calls == ["inject", "execute"]


def test_execution_core_returns_cancelled_result_before_execute() -> None:
    owner = _CancelledOwner()
    runtime_context = RuntimeContext()
    runtime_context.cancellation_context.request_cancel("stop node")

    result = ExecutionCore.execute_node(
        owner=owner,
        executable_node={"node_id": "node-a", "node_kind": "python.run"},
        runtime_context=runtime_context,
        data_edges_by_target={},
        executor_registry=object(),
    )

    assert result == {
        "status": "cancelled",
        "node_id": "node-a",
        "node_kind": "python.run",
        "message": "stop node",
        "reason": "stop node",
    }
    assert owner.calls == []


def test_execution_core_filters_control_edges_before_enqueue() -> None:
    captured: list[str] = []
    ExecutionCore.queue_control_edges(
        control_edges_by_source={
            "node-a": [
                {"edge_id": "edge-default", "from_port_id": None},
                {"edge_id": "edge-true", "from_port_id": "true"},
                {"edge_id": "edge-false", "from_port_id": "false"},
            ]
        },
        source_node_id="node-a",
        source_port_id="true",
        repeat_mode=False,
        enqueue=lambda edge, repeat_mode: captured.append(f"{edge['edge_id']}:{repeat_mode}"),
    )

    assert captured == ["edge-default:False", "edge-true:False"]


def test_execution_core_scheduler_snapshot_round_trip() -> None:
    executable_nodes = [
        {"node_id": "node-a", "node_kind": "control.while"},
        {"node_id": "node-b", "node_kind": "data.set_variable"},
    ]
    snapshot = ExecutionCore.build_scheduler_snapshot(
        scheduler_mode="flow_graph",
        pending_node_entries=[
            {"node_index": 1, "repeat_mode": True, "iteration_stack": ["node-a:2"]}
        ],
        queued_node_ids={"node-b"},
        executed_node_ids_in_order=["node-a"],
        join_state_by_node_id={"node-b": {"arrived_input_ports": {"left"}, "join_mode": "wait_all"}},
        retry_state_by_node_id={"node-a": {"attempts": 2}},
        executable_nodes=executable_nodes,
        current_program_counter=0,
        current_repeat_mode=True,
        current_iteration_stack=["node-a:2"],
    )

    restored = ExecutionCore.restore_scheduler_snapshot(
        snapshot=snapshot,
        executable_nodes=executable_nodes,
    )

    assert snapshot["current_node"]["node_id"] == "node-a"
    assert restored.pending_node_entries[0]["node_index"] == 1
    assert restored.pending_node_entries[0]["iteration_stack"] == ["node-a:2"]
    assert restored.queued_node_ids == {"node-b"}
    assert restored.join_state_by_node_id["node-b"]["arrived_tokens"] == {"left"}
    assert restored.retry_state_by_node_id["node-a"]["attempts"] == 2


def test_execution_core_scheduler_snapshot_preserves_network_context_references() -> None:
    executable_nodes = [
        {"node_id": "node-a", "node_kind": "network.http_request"},
        {"node_id": "node-b", "node_kind": "network.download"},
    ]
    snapshot = ExecutionCore.build_scheduler_snapshot(
        scheduler_mode="flow_graph",
        pending_node_entries=[
            {
                "node_index": 1,
                "repeat_mode": False,
                "iteration_stack": [],
                "token_context": {
                    "network_context_id": "network-context-queued",
                    "network_context_epoch": 4,
                },
            }
        ],
        queued_node_ids={"node-b"},
        executed_node_ids_in_order=["node-a"],
        join_state_by_node_id={},
        retry_state_by_node_id={},
        executable_nodes=executable_nodes,
        current_program_counter=0,
        current_repeat_mode=False,
        current_token_context=ExecutionTokenContext(
            network_context_id="network-context-current",
            network_context_epoch=3,
        ),
    )

    restored = ExecutionCore.restore_scheduler_snapshot(
        snapshot=snapshot,
        executable_nodes=executable_nodes,
    )

    assert snapshot["current_node"]["token_context"] == {
        "network_context_id": "network-context-current",
        "network_context_epoch": 3,
    }
    assert restored.pending_node_entries[0]["token_context"] == {
        "network_context_id": "network-context-queued",
        "network_context_epoch": 4,
    }


def test_cancellation_context_cleanup_is_idempotent_and_isolates_exceptions() -> None:
    context = RuntimeContext()
    calls: list[str] = []

    def broken_cleanup() -> None:
        calls.append("broken")
        raise RuntimeError("cleanup boom")

    def healthy_cleanup() -> None:
        calls.append("healthy")

    context.cancellation_context.register_cleanup(broken_cleanup)
    context.cancellation_context.register_cleanup(healthy_cleanup)

    context.cancellation_context.request_cancel("cancel once")
    context.cancellation_context.request_cancel("cancel twice")

    late_calls: list[str] = []
    context.cancellation_context.register_cleanup(lambda: late_calls.append("late"))

    assert calls == ["broken", "healthy"]
    assert late_calls == ["late"]
    assert context.cancellation_context.reason == "cancel once"


def test_runtime_context_close_is_idempotent_and_continues_cleanup() -> None:
    close_log: list[str] = []
    browser_context = _FakeClosable("browser_context", close_log, error=RuntimeError("context close failed"))
    browser = _FakeClosable("browser", close_log)
    playwright = _FakePlaywright(close_log)
    runtime_context = RuntimeContext(
        browser_runtime={
            "browser_context": browser_context,
            "browser": browser,
            "playwright": playwright,
        }
    )

    runtime_context.close()
    runtime_context.close()

    assert close_log == ["browser_context", "browser", "playwright"]
    assert browser_context.close_calls == 1
    assert browser.close_calls == 1
    assert playwright.stop_calls == 1


def test_runtime_context_close_does_not_cancel_borrowed_context() -> None:
    cancellation_context = CancellationContext()
    runtime_context = RuntimeContext(
        cancellation_context=cancellation_context,
        owns_cancellation_context=False,
    )

    runtime_context.close()

    assert cancellation_context.is_cancelled is False


def test_browser_wait_for_timeout_checks_cancellation_between_slices() -> None:
    runtime_context = RuntimeContext()
    page = _FakePage(runtime_context.cancellation_context)
    runtime_context.browser_runtime["page"] = page
    registry = RuntimeExecutorRegistry()

    with pytest.raises(RuntimeCancellationError, match="stop wait"):
        registry._execute_browser_wait_for_timeout(  # type: ignore[attr-defined]
            {"node_id": "node-a", "node_config": {"timeout": 200}},
            runtime_context,
        )

    assert page.wait_calls
    assert sum(page.wait_calls) < 200


def test_python_run_cancellation_terminates_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime_context = RuntimeContext(project_directory=tmp_path)
    fake_process = _FakePopen(runtime_context.cancellation_context)

    def fake_popen(*args: object, **kwargs: object) -> _FakePopen:
        return fake_process

    monkeypatch.setattr("weconduct.runtime.engine.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "weconduct.runtime.engine._validate_python_run_code",
        lambda code, blocked_imports: None,
    )
    registry = RuntimeExecutorRegistry(
        runtime_settings={
            "allow_python_execution": True,
            "python_project_runtime_enabled": True,
            "python_executable_path": "python",
            "python_project_runtime_root": str(tmp_path),
            "python_timeout_seconds": 5,
        }
    )

    with pytest.raises(RuntimeCancellationError, match="stop process"):
        registry._execute_python_run(  # type: ignore[attr-defined]
            {"node_id": "node-a", "node_config": {"code": "result = 1"}},
            runtime_context,
        )

    assert fake_process.terminate_calls == 1
    assert fake_process.kill_calls == 0


def test_http_request_registers_response_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_context = RuntimeContext()
    fake_response = _FakeHttpResponse(runtime_context.cancellation_context)

    monkeypatch.setattr(
        "weconduct.runtime.engine.urllib.request.urlopen",
        lambda request, timeout: fake_response,
    )
    monkeypatch.setattr(
        "weconduct.runtime.engine._validate_http_request_url",
        lambda url, **kwargs: url,
    )

    registry = RuntimeExecutorRegistry()

    with pytest.raises(RuntimeCancellationError, match="stop http"):
        registry._execute_http_request(  # type: ignore[attr-defined]
            {"node_id": "node-a", "node_config": {"url": "https://example.test"}},
            runtime_context,
        )

    assert fake_response.close_calls == 1


def test_http_request_preserves_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}
    runtime_context = RuntimeContext()
    response = _FakeHttpResponse(RuntimeContext().cancellation_context)

    def fake_urlopen(request: object, timeout: float) -> _FakeHttpResponse:
        observed["timeout"] = timeout
        return response

    monkeypatch.setattr(
        "weconduct.runtime.engine.urllib.request.urlopen",
        fake_urlopen,
    )
    monkeypatch.setattr(
        "weconduct.runtime.engine._validate_http_request_url",
        lambda url, **kwargs: url,
    )

    result = RuntimeExecutorRegistry()._execute_http_request(  # type: ignore[attr-defined]
        {"node_id": "node-a", "node_config": {"url": "https://example.test", "timeout": 12}},
        runtime_context,
    )

    assert result["status"] == "succeeded"
    assert observed["timeout"] == 12.0
    runtime_context.close()
    assert response.close_calls == 1


def test_browser_download_file_checks_cancellation_and_closes_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_context = RuntimeContext(project_directory=tmp_path)
    fake_response = _FakeStreamingResponse(runtime_context.cancellation_context)

    monkeypatch.setattr(
        "weconduct.runtime.engine.urllib.request.urlopen",
        lambda request, timeout=None: fake_response,
    )
    monkeypatch.setattr(
        "weconduct.runtime.engine._validate_http_request_url",
        lambda url, **kwargs: url,
    )

    with pytest.raises(RuntimeCancellationError, match="stop http"):
        RuntimeExecutorRegistry(
            runtime_settings={"allow_browser_downloads": True}
        )._execute_browser_download_file(  # type: ignore[attr-defined]
            {
                "node_id": "node-a",
                "node_config": {
                    "url": "https://example.test/file.bin",
                    "path": "download.bin",
                },
            },
            runtime_context,
        )

    assert fake_response.close_calls == 1


def test_runtime_context_unregisters_completed_cleanup() -> None:
    runtime_context = RuntimeContext()
    calls: list[str] = []
    unregister = runtime_context.register_cleanup("resource-1", lambda: calls.append("cleanup"))

    unregister()
    runtime_context.close()

    assert calls == []


def test_python_run_missing_child_result_uses_captured_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_context = RuntimeContext(project_directory=tmp_path)

    class _MissingResultPopen:
        def __init__(self) -> None:
            self.returncode = 7
            self.args = ["python", "runner.py"]

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            return ("captured stdout", "captured stderr")

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

    monkeypatch.setattr(
        "weconduct.runtime.engine.subprocess.Popen",
        lambda *args, **kwargs: _MissingResultPopen(),
    )
    monkeypatch.setattr(
        "weconduct.runtime.engine._validate_python_run_code",
        lambda code, blocked_imports: None,
    )

    result = RuntimeExecutorRegistry(
        runtime_settings={
            "allow_python_execution": True,
            "python_project_runtime_enabled": True,
            "python_executable_path": "python",
            "python_project_runtime_root": str(tmp_path),
            "python_timeout_seconds": 5,
        }
    )._execute_python_run(  # type: ignore[attr-defined]
        {"node_id": "node-a", "node_config": {"code": "result = 1"}},
        runtime_context,
    )

    assert result["status"] == "failed"
    assert "captured stdout" in result["message"]
    assert "captured stderr" in result["message"]
