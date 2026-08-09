from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
import subprocess

import pytest

from weconduct.application.execution_core import ExecutionCore
from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from weconduct.network_runtime.resources import ResponseBodyRef
from weconduct.runtime.engine import (
    CancellationContext,
    RuntimeCancellationError,
    RuntimeContext,
    RuntimeExecutorRegistry,
    _terminate_process,
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


def test_python_process_cleanup_terminates_windows_process_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _TreeProcess:
        pid = 2468

        def __init__(self) -> None:
            self.returncode: int | None = None
            self.communicate_calls = 0
            self.terminate_calls = 0
            self.kill_calls = 0

        def poll(self) -> int | None:
            return self.returncode

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            self.communicate_calls += 1
            self.returncode = -15
            return "", ""

        def terminate(self) -> None:
            self.terminate_calls += 1
            self.returncode = -15

        def kill(self) -> None:
            self.kill_calls += 1
            self.returncode = -9

    process = _TreeProcess()
    taskkill_calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        taskkill_calls.append((command, kwargs))
        process.returncode = -15
        return object()

    monkeypatch.setattr("weconduct.runtime.engine.os.name", "nt")
    monkeypatch.setattr("weconduct.runtime.engine.subprocess.run", fake_run)

    _terminate_process(process)  # type: ignore[arg-type]

    assert taskkill_calls == [
        (
            ["taskkill", "/PID", "2468", "/T", "/F"],
            {
                "check": False,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "creationflags": subprocess.CREATE_NO_WINDOW,
            },
        )
    ]
    assert process.terminate_calls == 0
    assert process.kill_calls == 0


def test_python_run_timeout_terminates_process_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _TimedOutProcess:
        args = ["python", "runner.py"]

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            raise subprocess.TimeoutExpired(self.args, timeout)

    process = _TimedOutProcess()
    terminated_processes: list[object] = []

    monkeypatch.setattr(
        "weconduct.runtime.engine.subprocess.Popen",
        lambda *args, **kwargs: process,
    )
    monkeypatch.setattr(
        "weconduct.runtime.engine._terminate_process",
        lambda target: terminated_processes.append(target),
    )
    monkeypatch.setattr(
        "weconduct.runtime.engine._validate_python_run_code",
        lambda code, blocked_imports: None,
    )

    output = RuntimeExecutorRegistry(
        runtime_settings={
            "allow_python_execution": True,
            "python_project_runtime_enabled": True,
            "python_executable_path": "python",
            "python_project_runtime_root": str(tmp_path),
            "python_timeout_seconds": 1,
        }
    )._execute_python_run(  # type: ignore[attr-defined]
        {"node_id": "python-timeout", "node_config": {"code": "result = 1"}},
        RuntimeContext(project_directory=tmp_path),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "python.execution_timeout"
    assert terminated_processes == [process]


def test_browser_download_file_uses_network_runtime_file_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_context = RuntimeContext(project_directory=tmp_path)
    response_path = tmp_path / "network-response.bin"
    response_path.write_bytes(b"download")

    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.operation: NetworkOperation | None = None
            self.snapshot: NetworkContextSnapshot | None = None
            self.cancelled_session_ids: list[str] = []

        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            self.operation = operation
            self.snapshot = snapshot
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                    final_url="https://example.test/final.bin",
                    body_ref=ResponseBodyRef(
                        session_id=operation.session_id,
                        storage_kind="file",
                        size_bytes=8,
                        content_type="application/octet-stream",
                        path=response_path,
                    ),
                )
            )
            return future

        def cancel_session(self, session_id: str) -> None:
            self.cancelled_session_ids.append(session_id)

    service = StubNetworkRuntimeService()

    validated_urls: list[str] = []
    monkeypatch.setattr(
        "weconduct.runtime.engine._validate_http_request_url",
        lambda url, **kwargs: (validated_urls.append(url), url)[1],
    )

    output = RuntimeExecutorRegistry(
        runtime_settings={"allow_browser_downloads": True},
        network_runtime_service=service,  # type: ignore[arg-type]
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

    assert service.operation is not None
    assert service.operation.method == "GET"
    assert service.operation.response_storage == "file"
    assert service.operation.session_id == "runtime-context"
    assert service.snapshot is not None
    assert service.snapshot.context_id == runtime_context.execution_token_context.network_context_id
    assert validated_urls == ["https://example.test/file.bin"]
    assert (tmp_path / "download.bin").read_bytes() == b"download"
    assert output == {
        "status": "succeeded",
        "node_id": "node-a",
        "url": "https://example.test/file.bin",
        "path": str((tmp_path / "download.bin").resolve()),
        "bytes_written": 8,
    }
    assert service.cancelled_session_ids == []


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
