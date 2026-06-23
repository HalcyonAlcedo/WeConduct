from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


PREFERENCES_FILE_VERSION = 1
FILE_ACCESS_SCOPES = {"restricted", "custom_roots", "allow_all"}


class PreferencesStore:
    def load(self) -> dict | None:
        raise NotImplementedError

    def save(self, preferences: dict) -> None:
        raise NotImplementedError


class InMemoryPreferencesStore(PreferencesStore):
    def __init__(self, initial_preferences: dict | None = None) -> None:
        self._preferences = deepcopy(initial_preferences) if initial_preferences is not None else None

    def load(self) -> dict | None:
        if self._preferences is None:
            return None
        return deepcopy(self._preferences)

    def save(self, preferences: dict) -> None:
        self._preferences = deepcopy(preferences)


class FilePreferencesStore(PreferencesStore):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> dict | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("preferences file must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("preferences file must be a JSON object")
        self._validate_payload(payload)
        return payload

    def save(self, preferences: dict) -> None:
        self._validate_payload(preferences)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(preferences, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self._path)

    def _validate_payload(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            raise ValueError("preferences must be a JSON object")
        required_keys = {
            "preferences_file_version",
            "program_settings",
            "compile_settings",
            "security_settings",
            "python_runtime_settings",
            "graph_settings",
            "other_settings",
        }
        for key in required_keys:
            if key not in payload:
                raise ValueError(f"preferences file missing required key: {key}")
        if payload["preferences_file_version"] != PREFERENCES_FILE_VERSION:
            raise ValueError(
                "preferences file version mismatch: "
                f"expected {PREFERENCES_FILE_VERSION}, got {payload['preferences_file_version']}"
            )


def build_default_preferences() -> dict:
    return {
        "preferences_file_version": PREFERENCES_FILE_VERSION,
        "program_settings": {
            "language": "zh-CN",
            "resource_language": "zh-CN",
            "theme": "light",
            "default_window_size": {
                "width": 1440,
                "height": 900,
            },
            "startup_action": "restore_last_workspace",
            "default_project_directory": None,
            "recent_project_limit": 10,
            "preferences_auto_save": True,
            "font_scale": 100,
        },
        "compile_settings": {
            "default_source_kind": "graph_workspace",
            "diagnostic_level": "error",
            "block_on_disabled_components": True,
            "allow_degraded_compile": True,
            "stop_on_first_error": True,
            "emit_runtime_plan": True,
            "emit_debug_plan": True,
        },
        "security_settings": {
            "confirm_high_risk_actions": True,
            "allow_external_programs": False,
            "allow_file_access": False,
            "file_access_scope": "restricted",
            "file_access_allowed_roots": [],
            "file_access_blocked_roots": [],
            "file_access_allowed_extensions": [],
            "file_access_blocked_extensions": [],
            "file_access_require_absolute_path": False,
            "allow_browser_executor": False,
            "allow_browser_screenshots": True,
            "allow_cookie_manipulation": True,
            "allow_browser_storage_manipulation": True,
            "allow_browser_uploads": True,
            "allow_browser_downloads": False,
            "allow_new_browser_windows": True,
            "allow_local_network_access": False,
            "allow_remote_network_access": False,
            "allow_python_execution": False,
            "allow_js_injection": False,
            "allow_js_evaluation": False,
            "show_security_warnings_in_runtime": True,
            "log_security_events": True,
        },
        "python_runtime_settings": {
            "python_executable_path": None,
            "timeout_seconds": 60,
            "sandbox_mode": "restricted",
            "capture_stdout_stderr": True,
        },
        "graph_settings": {
            "auto_sync_mode": "responsive",
            "save_conflict_policy": "prefer_current_graph",
            "show_node_id_on_node": True,
            "show_disabled_resource_badge": True,
            "snap_to_grid": True,
            "grid_enabled": True,
            "auto_open_node_on_drop": True,
            "confirm_delete_node": True,
            "show_inline_config_summary": True,
        },
        "other_settings": {
            "workspace_draft_recovery_enabled": True,
            "workspace_draft_recovery_ttl_minutes": 30,
        },
    }


def normalize_preferences(preferences: dict | None) -> tuple[dict, bool]:
    if preferences is None:
        return build_default_preferences(), True
    if not isinstance(preferences, dict):
        raise ValueError("preferences must be a JSON object")
    changed = False
    normalized = build_default_preferences()
    for key, value in preferences.items():
        if key in normalized and key != "preferences_file_version" and isinstance(value, dict):
            normalized[key].update(value)
            if normalized[key] != value:
                changed = True
        elif key == "preferences_file_version":
            normalized[key] = value
        else:
            normalized[key] = deepcopy(value)
    for key in normalized:
        if key not in preferences:
            changed = True
    normalized_security_settings = _normalize_security_settings(normalized["security_settings"])
    if normalized_security_settings != normalized["security_settings"]:
        normalized["security_settings"] = normalized_security_settings
        changed = True
    return normalized, changed


def _normalize_security_settings(settings: Any) -> dict:
    defaults = build_default_preferences()["security_settings"]
    if not isinstance(settings, dict):
        return deepcopy(defaults)
    normalized = deepcopy(defaults)
    normalized["confirm_high_risk_actions"] = bool(
        settings.get("confirm_high_risk_actions", defaults["confirm_high_risk_actions"])
    )
    normalized["allow_external_programs"] = bool(
        settings.get("allow_external_programs", defaults["allow_external_programs"])
    )
    normalized["allow_file_access"] = bool(
        settings.get("allow_file_access", defaults["allow_file_access"])
    )
    file_access_scope = settings.get("file_access_scope", defaults["file_access_scope"])
    normalized["file_access_scope"] = (
        file_access_scope if file_access_scope in FILE_ACCESS_SCOPES else defaults["file_access_scope"]
    )
    normalized["file_access_allowed_roots"] = _normalize_path_list(
        settings.get("file_access_allowed_roots", defaults["file_access_allowed_roots"])
    )
    normalized["file_access_blocked_roots"] = _normalize_path_list(
        settings.get("file_access_blocked_roots", defaults["file_access_blocked_roots"])
    )
    normalized["file_access_allowed_extensions"] = _normalize_extension_list(
        settings.get(
            "file_access_allowed_extensions",
            defaults["file_access_allowed_extensions"],
        )
    )
    normalized["file_access_blocked_extensions"] = _normalize_extension_list(
        settings.get(
            "file_access_blocked_extensions",
            defaults["file_access_blocked_extensions"],
        )
    )
    normalized["file_access_require_absolute_path"] = bool(
        settings.get(
            "file_access_require_absolute_path",
            defaults["file_access_require_absolute_path"],
        )
    )
    normalized["allow_browser_executor"] = bool(
        settings.get("allow_browser_executor", defaults["allow_browser_executor"])
    )
    normalized["allow_browser_screenshots"] = bool(
        settings.get(
            "allow_browser_screenshots",
            defaults["allow_browser_screenshots"],
        )
    )
    normalized["allow_cookie_manipulation"] = bool(
        settings.get(
            "allow_cookie_manipulation",
            defaults["allow_cookie_manipulation"],
        )
    )
    normalized["allow_browser_storage_manipulation"] = bool(
        settings.get(
            "allow_browser_storage_manipulation",
            defaults["allow_browser_storage_manipulation"],
        )
    )
    normalized["allow_browser_uploads"] = bool(
        settings.get(
            "allow_browser_uploads",
            defaults["allow_browser_uploads"],
        )
    )
    normalized["allow_browser_downloads"] = bool(
        settings.get(
            "allow_browser_downloads",
            defaults["allow_browser_downloads"],
        )
    )
    normalized["allow_new_browser_windows"] = bool(
        settings.get(
            "allow_new_browser_windows",
            defaults["allow_new_browser_windows"],
        )
    )
    normalized["allow_local_network_access"] = bool(
        settings.get("allow_local_network_access", defaults["allow_local_network_access"])
    )
    normalized["allow_remote_network_access"] = bool(
        settings.get(
            "allow_remote_network_access",
            defaults["allow_remote_network_access"],
        )
    )
    normalized["allow_python_execution"] = bool(
        settings.get(
            "allow_python_execution",
            defaults["allow_python_execution"],
        )
    )
    normalized["allow_js_injection"] = bool(
        settings.get(
            "allow_js_injection",
            defaults["allow_js_injection"],
        )
    )
    normalized["allow_js_evaluation"] = bool(
        settings.get(
            "allow_js_evaluation",
            defaults["allow_js_evaluation"],
        )
    )
    normalized["show_security_warnings_in_runtime"] = bool(
        settings.get(
            "show_security_warnings_in_runtime",
            defaults["show_security_warnings_in_runtime"],
        )
    )
    normalized["log_security_events"] = bool(
        settings.get("log_security_events", defaults["log_security_events"])
    )
    return normalized


def _normalize_path_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    normalized: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if not trimmed:
            continue
        if trimmed not in normalized:
            normalized.append(trimmed)
    return normalized


def _normalize_extension_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    normalized: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            continue
        trimmed = item.strip().lower()
        if not trimmed:
            continue
        if trimmed not in normalized:
            normalized.append(trimmed)
    return normalized
