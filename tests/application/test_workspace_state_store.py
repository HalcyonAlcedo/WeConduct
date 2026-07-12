from pathlib import Path

import pytest

from weconduct.application.workspace_state_store import FileWorkspaceStateStore


def test_file_workspace_state_store_retries_transient_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "runtime" / "workspace-state.json"
    store = FileWorkspaceStateStore(state_path)
    state = {
        "workspace_state_version": 1,
        "workbench": {},
        "last_compile": None,
        "compile_history": [],
    }
    original_replace = Path.replace
    replace_attempt_count = 0

    def transient_replace_failure(path: Path, target: Path) -> Path:
        nonlocal replace_attempt_count
        if Path(target) == state_path:
            replace_attempt_count += 1
            if replace_attempt_count < 3:
                raise PermissionError("workspace state target is temporarily locked")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", transient_replace_failure)

    store.save(state)

    assert replace_attempt_count == 3
    assert store.load() == state
