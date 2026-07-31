from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from weconduct.application.compilation_workbench_service import CompilationWorkbenchService
from weconduct.application.workspace_state_store import FileWorkspaceStateStore


def _prepare_dirty_project(tmp_path: Path) -> tuple[FileWorkspaceStateStore, str]:
    state_store = FileWorkspaceStateStore(tmp_path / "runtime" / "workspace-state.json")
    service = CompilationWorkbenchService(state_store=state_store)
    service.create_project(project_name="Repro Project")
    project_path = tmp_path / "Repro Project.weconduct.json"
    service.save_project_as(project_path=project_path)

    graph = service.get_graph_document()["graph_model"].model_dump(mode="json")
    graph["nodes"] = [
        service.build_graph_node_draft(
            resource_key="message.emit",
            node_id="message-1",
        )["node"]
    ]
    service.save_graph_document(graph)
    return state_store, str(project_path)


def test_startup_restores_dirty_project_graph_without_emptying_workspace(tmp_path: Path) -> None:
    state_store, project_path = _prepare_dirty_project(tmp_path)

    restarted = CompilationWorkbenchService(state_store=state_store)
    snapshot = restarted.get_workbench_snapshot()
    graph = restarted.get_graph_document()["graph_model"]

    assert snapshot["project"]["loaded"] is True
    assert snapshot["project"]["project_name"] == "Repro Project"
    assert snapshot["project"]["project_file_path"] == project_path
    assert snapshot["project"]["is_dirty"] is True
    assert snapshot["project"]["pending_recovery"] is None
    assert [node.node_id for node in graph.nodes] == ["message-1"]


def test_startup_auto_restores_legacy_pending_recovery_state(tmp_path: Path) -> None:
    state_store, _ = _prepare_dirty_project(tmp_path)
    state = state_store.load()
    assert state is not None

    project = state["project"]
    project_runtime = state["project_runtime"]
    recovery_workspace_state = deepcopy(state)
    recovery_workspace_state["pending_recovery"] = None
    legacy_state = CompilationWorkbenchService()._build_initial_workspace_state(
        project_name=project["project_name"],
        project_id=project["project_id"],
        project_file_path=project_runtime["project_file_path"],
        mark_project_dirty=False,
    )
    legacy_state["recent_projects"] = deepcopy(state["recent_projects"])
    legacy_state["pending_recovery"] = {
        "status": "pending",
        "project_id": project["project_id"],
        "project_name": project["project_name"],
        "project_file_path": project_runtime["project_file_path"],
        "workspace_state": recovery_workspace_state,
    }
    state_store.save(legacy_state)

    restarted = CompilationWorkbenchService(state_store=state_store)
    snapshot = restarted.get_workbench_snapshot()
    graph = restarted.get_graph_document()["graph_model"]

    assert snapshot["project"]["pending_recovery"] is None
    assert [node.node_id for node in graph.nodes] == ["message-1"]
