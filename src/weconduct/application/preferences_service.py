from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .preferences_store import (
    FILE_ACCESS_SCOPES,
    FilePreferencesStore,
    PreferencesStore,
    build_default_preferences,
    normalize_preferences,
)


class HighRiskPreferenceChangeRequiredError(ValueError):
    def __init__(self, *, section: str, high_risk_changes: list[dict]) -> None:
        super().__init__("high-risk preference changes require confirmation")
        self.section = section
        self.high_risk_changes = [dict(item) for item in high_risk_changes]
        self.requires_confirmation = True


class PreferencesService:
    def __init__(self, *, preferences_store: PreferencesStore | None = None) -> None:
        self._preferences_store = preferences_store or FilePreferencesStore(
            self._resolve_default_preferences_path()
        )
        self._preferences = self._load_preferences()

    def get_preferences_document(self) -> dict:
        return deepcopy(self._preferences)

    def preview_preferences_update(self, *, section: str, values: dict) -> dict:
        current_section, next_section, confirmation_required, high_risk_changes = (
            self._build_preferences_update_preview(section=section, values=values)
        )
        return {
            "section": section,
            "current_values": current_section,
            "proposed_values": next_section,
            "confirmation_required": confirmation_required,
            "high_risk_changes": high_risk_changes,
        }

    def update_preferences(
        self,
        *,
        section: str,
        values: dict,
        confirm_high_risk: bool = False,
    ) -> dict:
        if section not in self._preferences:
            raise ValueError(f"preferences section not found: {section}")
        if section == "preferences_file_version":
            raise ValueError("preferences_file_version is read-only")
        _, next_section, confirmation_required, high_risk_changes = (
            self._build_preferences_update_preview(section=section, values=values)
        )
        if confirmation_required and not confirm_high_risk:
            raise HighRiskPreferenceChangeRequiredError(
                section=section,
                high_risk_changes=high_risk_changes,
            )
        self._preferences[section] = next_section
        self._persist()
        return self.get_preferences_document()

    def reset_preferences(self) -> dict:
        self._preferences = build_default_preferences()
        self._persist()
        return self.get_preferences_document()

    def _load_preferences(self) -> dict:
        loaded = self._preferences_store.load()
        normalized, changed = normalize_preferences(loaded)
        if changed:
            self._preferences_store.save(normalized)
        return normalized

    def _persist(self) -> None:
        self._preferences_store.save(self._preferences)

    def _resolve_default_preferences_path(self) -> Path:
        local_app_data = Path.home()
        return local_app_data / "AppData" / "Local" / "WeConduct" / "preferences.json"

    def _build_preferences_update_preview(
        self,
        *,
        section: str,
        values: dict,
    ) -> tuple[dict, dict, bool, list[dict]]:
        if section not in self._preferences:
            raise ValueError(f"preferences section not found: {section}")
        if section == "preferences_file_version":
            raise ValueError("preferences_file_version is read-only")
        if not isinstance(values, dict):
            raise ValueError("values must be a JSON object")
        current_section = dict(self._preferences[section])
        self._validate_section_update(section=section, values=values)
        candidate = self.get_preferences_document()
        merged_section = dict(current_section)
        merged_section.update(deepcopy(values))
        candidate[section] = merged_section
        normalized_candidate, _ = normalize_preferences(candidate)
        next_section = dict(normalized_candidate[section])
        high_risk_changes = self._collect_high_risk_changes(
            section=section,
            current_section=current_section,
            next_section=next_section,
        )
        confirmation_required = bool(
            current_section.get("confirm_high_risk_actions", True)
            and high_risk_changes
        )
        return current_section, next_section, confirmation_required, high_risk_changes

    def _validate_section_update(self, *, section: str, values: dict) -> None:
        if section == "python_runtime_settings":
            if "blocked_import_modules" in values:
                raw_modules = values["blocked_import_modules"]
                if not isinstance(raw_modules, list):
                    raise ValueError(
                        "field must be a JSON string array with non-empty items: blocked_import_modules"
                    )
            return
        if section != "security_settings":
            return
        bool_fields = {
            "confirm_high_risk_actions",
            "allow_external_programs",
            "allow_file_access",
            "file_access_require_absolute_path",
            "allow_browser_executor",
            "allow_browser_screenshots",
            "allow_cookie_manipulation",
            "allow_browser_storage_manipulation",
            "allow_browser_uploads",
            "allow_browser_downloads",
            "allow_new_browser_windows",
            "allow_local_network_access",
            "allow_remote_network_access",
            "allow_python_execution",
            "allow_js_injection",
            "allow_js_evaluation",
            "show_security_warnings_in_runtime",
            "log_security_events",
        }
        for field in bool_fields:
            if field in values and not isinstance(values[field], bool):
                raise ValueError(f"field must be a boolean: {field}")
        if "file_access_scope" in values:
            scope = values["file_access_scope"]
            if not isinstance(scope, str) or scope not in FILE_ACCESS_SCOPES:
                raise ValueError(
                    "field must be one of restricted, custom_roots, allow_all: file_access_scope"
                )
        if "file_access_allowed_roots" in values:
            raw_roots = values["file_access_allowed_roots"]
            if not isinstance(raw_roots, list) or any(
                not isinstance(item, str) or not item.strip() for item in raw_roots
            ):
                raise ValueError(
                    "field must be a JSON string array with non-empty items: file_access_allowed_roots"
                )
        for field_name in (
            "file_access_blocked_roots",
            "file_access_allowed_extensions",
            "file_access_blocked_extensions",
        ):
            if field_name not in values:
                continue
            raw_items = values[field_name]
            if not isinstance(raw_items, list) or any(
                not isinstance(item, str) or not item.strip() for item in raw_items
            ):
                raise ValueError(
                    f"field must be a JSON string array with non-empty items: {field_name}"
                )

    def _collect_high_risk_changes(
        self,
        *,
        section: str,
        current_section: dict,
        next_section: dict,
    ) -> list[dict]:
        if section != "security_settings":
            return []
        changes: list[dict] = []
        high_risk_rules = [
            (
                "allow_external_programs",
                "enables external program execution",
                lambda before, after: before is False and after is True,
            ),
            (
                "allow_browser_executor",
                "enables browser automation execution",
                lambda before, after: before is False and after is True,
            ),
            (
                "allow_local_network_access",
                "enables local network access",
                lambda before, after: before is False and after is True,
            ),
            (
                "allow_python_execution",
                "enables python code execution",
                lambda before, after: before is False and after is True,
            ),
            (
                "allow_js_injection",
                "enables JavaScript injection",
                lambda before, after: before is False and after is True,
            ),
            (
                "allow_js_evaluation",
                "enables JavaScript evaluation",
                lambda before, after: before is False and after is True,
            ),
            (
                "allow_remote_network_access",
                "enables remote network access",
                lambda before, after: before is False and after is True,
            ),
            (
                "file_access_scope",
                "allows file access outside configured directories",
                lambda before, after: before != "allow_all" and after == "allow_all",
            ),
            (
                "file_access_require_absolute_path",
                "allows relative file paths during runtime",
                lambda before, after: before is True and after is False,
            ),
        ]
        for field, reason, predicate in high_risk_rules:
            before = current_section.get(field)
            after = next_section.get(field)
            if predicate(before, after):
                changes.append(
                    {
                        "field": field,
                        "from": before,
                        "to": after,
                        "reason": reason,
                    }
                )
        return changes
