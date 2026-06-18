from pathlib import Path

import pytest

from weconduct.application.preferences_service import PreferencesService
from weconduct.application.preferences_store import FilePreferencesStore, InMemoryPreferencesStore


def test_preferences_service_builds_default_preferences_document() -> None:
    service = PreferencesService(preferences_store=InMemoryPreferencesStore())

    document = service.get_preferences_document()

    assert document["preferences_file_version"] == 1
    assert document["program_settings"]["language"] == "zh-CN"
    assert document["program_settings"]["resource_language"] == "zh-CN"
    assert document["program_settings"]["preferences_auto_save"] is True
    assert document["program_settings"]["default_window_size"] == {
        "width": 1440,
        "height": 900,
    }
    assert document["program_settings"]["font_scale"] == 100
    assert document["compile_settings"]["block_on_disabled_components"] is True
    assert document["compile_settings"]["stop_on_first_error"] is True
    assert document["compile_settings"]["emit_runtime_plan"] is True
    assert document["compile_settings"]["emit_debug_plan"] is True
    assert document["security_settings"]["allow_browser_executor"] is True
    assert document["security_settings"]["allow_local_network_access"] is True
    assert document["python_runtime_settings"]["capture_stdout_stderr"] is True
    assert document["graph_settings"]["auto_sync_mode"] == "responsive"
    assert document["graph_settings"]["save_conflict_policy"] == "prefer_current_graph"
    assert document["graph_settings"]["auto_open_node_on_drop"] is True
    assert document["graph_settings"]["confirm_delete_node"] is True
    assert document["graph_settings"]["show_inline_config_summary"] is True
    assert document["other_settings"]["workspace_draft_recovery_enabled"] is True
    assert document["other_settings"]["workspace_draft_recovery_ttl_minutes"] == 30


def test_preferences_service_can_update_program_settings() -> None:
    store = InMemoryPreferencesStore()
    service = PreferencesService(preferences_store=store)

    document = service.update_preferences(
        section="program_settings",
        values={"language": "en-US", "theme": "dark"},
    )

    assert document["program_settings"]["language"] == "en-US"
    assert document["program_settings"]["theme"] == "dark"
    assert store.load()["program_settings"]["language"] == "en-US"


def test_preferences_service_can_update_graph_settings_save_conflict_policy() -> None:
    store = InMemoryPreferencesStore()
    service = PreferencesService(preferences_store=store)

    document = service.update_preferences(
        section="graph_settings",
        values={"save_conflict_policy": "strict"},
    )

    assert document["graph_settings"]["save_conflict_policy"] == "strict"
    assert store.load()["graph_settings"]["save_conflict_policy"] == "strict"


def test_file_preferences_store_rejects_missing_version(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    path.write_text(
        """
{
  "program_settings": {}
}
""".strip(),
        encoding="utf-8",
    )

    store = FilePreferencesStore(path)

    with pytest.raises(ValueError, match="preferences file missing required key"):
        store.load()
