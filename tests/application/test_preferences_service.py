from pathlib import Path

import pytest

from weconduct.application.preferences_service import (
    HighRiskPreferenceChangeRequiredError,
    PreferencesService,
)
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
    assert document["security_settings"]["allow_file_access"] is False
    assert document["security_settings"]["file_access_scope"] == "restricted"
    assert document["security_settings"]["file_access_allowed_roots"] == []
    assert document["security_settings"]["file_access_blocked_roots"] == []
    assert document["security_settings"]["file_access_allowed_extensions"] == []
    assert document["security_settings"]["file_access_blocked_extensions"] == []
    assert document["security_settings"]["file_access_require_absolute_path"] is False
    assert document["security_settings"]["allow_browser_executor"] is False
    assert document["security_settings"]["allow_browser_screenshots"] is True
    assert document["security_settings"]["allow_cookie_manipulation"] is True
    assert document["security_settings"]["allow_browser_storage_manipulation"] is True
    assert document["security_settings"]["allow_browser_uploads"] is True
    assert document["security_settings"]["allow_browser_downloads"] is False
    assert document["security_settings"]["allow_new_browser_windows"] is True
    assert document["security_settings"]["allow_local_network_access"] is False
    assert document["security_settings"]["allow_remote_network_access"] is False
    assert document["security_settings"]["allow_python_execution"] is False
    assert document["security_settings"]["allow_js_injection"] is False
    assert document["security_settings"]["allow_js_evaluation"] is False
    assert document["security_settings"]["show_security_warnings_in_runtime"] is True
    assert document["security_settings"]["log_security_events"] is True
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


def test_preferences_service_normalizes_missing_security_fields_from_legacy_document() -> None:
    store = InMemoryPreferencesStore(
        {
            "preferences_file_version": 1,
            "program_settings": {},
            "compile_settings": {},
            "security_settings": {
                "confirm_high_risk_actions": True,
                "allow_file_access": True,
            },
            "python_runtime_settings": {},
            "graph_settings": {},
            "other_settings": {},
        }
    )

    service = PreferencesService(preferences_store=store)

    document = service.get_preferences_document()

    assert document["security_settings"]["allow_file_access"] is True
    assert document["security_settings"]["file_access_scope"] == "restricted"
    assert document["security_settings"]["file_access_allowed_roots"] == []
    assert document["security_settings"]["file_access_blocked_roots"] == []
    assert document["security_settings"]["file_access_allowed_extensions"] == []
    assert document["security_settings"]["file_access_blocked_extensions"] == []
    assert document["security_settings"]["file_access_require_absolute_path"] is False
    assert document["security_settings"]["allow_browser_screenshots"] is True
    assert document["security_settings"]["allow_cookie_manipulation"] is True
    assert document["security_settings"]["allow_browser_storage_manipulation"] is True
    assert document["security_settings"]["allow_browser_uploads"] is True
    assert document["security_settings"]["allow_browser_downloads"] is False
    assert document["security_settings"]["allow_new_browser_windows"] is True
    assert document["security_settings"]["allow_remote_network_access"] is False
    assert document["security_settings"]["allow_python_execution"] is False
    assert document["security_settings"]["allow_js_injection"] is False
    assert document["security_settings"]["allow_js_evaluation"] is False
    assert document["security_settings"]["show_security_warnings_in_runtime"] is True
    assert document["security_settings"]["log_security_events"] is True
    assert store.load()["security_settings"]["file_access_scope"] == "restricted"
    assert store.load()["security_settings"]["file_access_allowed_roots"] == []
    assert store.load()["security_settings"]["file_access_blocked_roots"] == []
    assert store.load()["security_settings"]["file_access_allowed_extensions"] == []
    assert store.load()["security_settings"]["file_access_blocked_extensions"] == []
    assert store.load()["security_settings"]["file_access_require_absolute_path"] is False
    assert store.load()["security_settings"]["show_security_warnings_in_runtime"] is True
    assert store.load()["security_settings"]["log_security_events"] is True


def test_preferences_service_normalizes_extended_security_lists_and_invalid_values() -> None:
    store = InMemoryPreferencesStore(
        {
            "preferences_file_version": 1,
            "program_settings": {},
            "compile_settings": {},
            "security_settings": {
                "allow_file_access": True,
                "file_access_allowed_roots": [" C:\\allowed ", "", "C:\\allowed", 123],
                "file_access_blocked_roots": [" C:\\blocked ", "C:\\blocked"],
                "file_access_allowed_extensions": [" .txt ", ".txt", "", 9],
                "file_access_blocked_extensions": [".exe", " exe ", None],
                "file_access_require_absolute_path": True,
                "allow_browser_screenshots": False,
                "allow_cookie_manipulation": False,
                "allow_browser_storage_manipulation": False,
                "allow_browser_uploads": False,
                "allow_browser_downloads": True,
                "allow_new_browser_windows": False,
                "allow_remote_network_access": True,
                "allow_python_execution": True,
                "allow_js_injection": True,
                "allow_js_evaluation": True,
                "log_security_events": False,
            },
            "python_runtime_settings": {},
            "graph_settings": {},
            "other_settings": {},
        }
    )

    service = PreferencesService(preferences_store=store)

    document = service.get_preferences_document()

    assert document["security_settings"]["file_access_allowed_roots"] == ["C:\\allowed"]
    assert document["security_settings"]["file_access_blocked_roots"] == ["C:\\blocked"]
    assert document["security_settings"]["file_access_allowed_extensions"] == [".txt"]
    assert document["security_settings"]["file_access_blocked_extensions"] == [".exe", "exe"]
    assert document["security_settings"]["file_access_require_absolute_path"] is True
    assert document["security_settings"]["allow_browser_screenshots"] is False
    assert document["security_settings"]["allow_cookie_manipulation"] is False
    assert document["security_settings"]["allow_browser_storage_manipulation"] is False
    assert document["security_settings"]["allow_browser_uploads"] is False
    assert document["security_settings"]["allow_browser_downloads"] is True
    assert document["security_settings"]["allow_new_browser_windows"] is False
    assert document["security_settings"]["allow_remote_network_access"] is True
    assert document["security_settings"]["allow_python_execution"] is True
    assert document["security_settings"]["allow_js_injection"] is True
    assert document["security_settings"]["allow_js_evaluation"] is True
    assert document["security_settings"]["log_security_events"] is False


def test_preferences_service_rejects_high_risk_security_update_without_confirmation() -> None:
    store = InMemoryPreferencesStore()
    service = PreferencesService(preferences_store=store)

    with pytest.raises(HighRiskPreferenceChangeRequiredError) as exc_info:
        service.update_preferences(
            section="security_settings",
            values={"allow_external_programs": True},
        )

    error = exc_info.value
    assert error.section == "security_settings"
    assert error.requires_confirmation is True
    assert error.high_risk_changes == [
        {
            "field": "allow_external_programs",
            "from": False,
            "to": True,
            "reason": "enables external program execution",
        }
    ]


def test_preferences_service_allows_high_risk_security_update_after_confirmation() -> None:
    store = InMemoryPreferencesStore()
    service = PreferencesService(preferences_store=store)

    document = service.update_preferences(
        section="security_settings",
        values={"allow_external_programs": True, "file_access_scope": "allow_all"},
        confirm_high_risk=True,
    )

    assert document["security_settings"]["allow_external_programs"] is True
    assert document["security_settings"]["file_access_scope"] == "allow_all"
    assert store.load()["security_settings"]["allow_external_programs"] is True
    assert store.load()["security_settings"]["file_access_scope"] == "allow_all"


def test_preferences_service_preview_reports_high_risk_security_changes() -> None:
    service = PreferencesService(preferences_store=InMemoryPreferencesStore())

    preview = service.preview_preferences_update(
        section="security_settings",
        values={"allow_local_network_access": True, "file_access_scope": "allow_all"},
    )

    assert preview["confirmation_required"] is True
    assert preview["high_risk_changes"] == [
        {
            "field": "allow_local_network_access",
            "from": False,
            "to": True,
            "reason": "enables local network access",
        },
        {
            "field": "file_access_scope",
            "from": "restricted",
            "to": "allow_all",
            "reason": "allows file access outside configured directories",
        },
    ]
    assert preview["proposed_values"]["allow_local_network_access"] is True
    assert preview["proposed_values"]["file_access_scope"] == "allow_all"


def test_preferences_service_preview_reports_extended_high_risk_security_changes() -> None:
    service = PreferencesService(preferences_store=InMemoryPreferencesStore())

    preview = service.preview_preferences_update(
        section="security_settings",
        values={
            "allow_python_execution": True,
            "allow_js_injection": True,
            "allow_js_evaluation": True,
            "allow_remote_network_access": True,
        },
    )

    assert preview["confirmation_required"] is True
    assert preview["high_risk_changes"] == [
        {
            "field": "allow_python_execution",
            "from": False,
            "to": True,
            "reason": "enables python code execution",
        },
        {
            "field": "allow_js_injection",
            "from": False,
            "to": True,
            "reason": "enables JavaScript injection",
        },
        {
            "field": "allow_js_evaluation",
            "from": False,
            "to": True,
            "reason": "enables JavaScript evaluation",
        },
        {
            "field": "allow_remote_network_access",
            "from": False,
            "to": True,
            "reason": "enables remote network access",
        },
    ]


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
