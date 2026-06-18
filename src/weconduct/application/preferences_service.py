from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .preferences_store import (
    FilePreferencesStore,
    PreferencesStore,
    build_default_preferences,
    normalize_preferences,
)


class PreferencesService:
    def __init__(self, *, preferences_store: PreferencesStore | None = None) -> None:
        self._preferences_store = preferences_store or FilePreferencesStore(
            self._resolve_default_preferences_path()
        )
        self._preferences = self._load_preferences()

    def get_preferences_document(self) -> dict:
        return deepcopy(self._preferences)

    def update_preferences(self, *, section: str, values: dict) -> dict:
        if section not in self._preferences:
            raise ValueError(f"preferences section not found: {section}")
        if section == "preferences_file_version":
            raise ValueError("preferences_file_version is read-only")
        current = dict(self._preferences[section])
        current.update(values)
        self._preferences[section] = current
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
