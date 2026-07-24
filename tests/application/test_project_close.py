from __future__ import annotations

import pytest

from weconduct.application.compilation_workbench_service import CompilationWorkbenchService


def test_project_close_rejects_unsaved_changes_without_discard() -> None:
    service = CompilationWorkbenchService()
    service.create_project(project_name="close-test")
    service.update_project_settings(
        project_settings={
            **service.get_project_settings_document()["project_settings"],
            "project_identity": {"name": "changed"},
        }
    )

    with pytest.raises(ValueError, match="unsaved"):
        service.close_project()


def test_project_close_resets_workspace_when_discard_is_explicit() -> None:
    service = CompilationWorkbenchService()
    service.create_project(project_name="close-test")

    result = service.close_project(discard_changes=True)

    assert result["status"] == "closed"
    assert result["project"]["project_name"] == "WeConduct Workspace"
