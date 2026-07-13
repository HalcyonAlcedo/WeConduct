from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Callable

from .repository import ConfigurationRepository


GRAPH_CONFIGURATION_FORMAT_VERSION = 1


class FileGraphConfigurationRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict:
        payload = self._read_payload()
        values = payload.get("values") if self.is_current_payload(payload) else None
        return deepcopy(values) if isinstance(values, dict) else {}

    def save(self, payload: dict) -> None:
        document = {
            "configuration_format_version": GRAPH_CONFIGURATION_FORMAT_VERSION,
            "scope": "graph",
            "values": deepcopy(payload),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(f".{self.path.name}.tmp")
        temporary_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary_path.replace(self.path)

    def is_current(self) -> bool:
        return self.is_current_payload(self._read_payload())

    @staticmethod
    def is_current_payload(payload: object) -> bool:
        return (
            isinstance(payload, dict)
            and payload.get("configuration_format_version") == GRAPH_CONFIGURATION_FORMAT_VERSION
            and payload.get("scope") == "graph"
            and isinstance(payload.get("values"), dict)
        )

    def _read_payload(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}


class WorkbenchGraphConfigurationRepository:
    """Combines persisted editor preferences with the bound graph entrypoint."""

    def __init__(
        self,
        *,
        editor_repository: ConfigurationRepository,
        get_entrypoint_runtime: Callable[[], dict],
        update_entrypoint_runtime: Callable[[dict], None],
    ) -> None:
        self._editor_repository = editor_repository
        self._get_entrypoint_runtime = get_entrypoint_runtime
        self._update_entrypoint_runtime = update_entrypoint_runtime

    def load(self) -> dict:
        stored = self._editor_repository.load()
        editor_preferences = (
            stored.get("editor_preferences")
            if isinstance(stored.get("editor_preferences"), dict)
            else {}
        )
        runtime = self._get_entrypoint_runtime()
        return {
            "editor_preferences": deepcopy(editor_preferences),
            "entrypoint_runtime": deepcopy(runtime) if isinstance(runtime, dict) else {},
        }

    def save(self, payload: dict) -> None:
        editor_preferences = payload.get("editor_preferences")
        self._editor_repository.save(
            {
                "editor_preferences": deepcopy(editor_preferences)
                if isinstance(editor_preferences, dict)
                else {},
            }
        )
        entrypoint_runtime = payload.get("entrypoint_runtime")
        if not isinstance(entrypoint_runtime, dict):
            return
        current_runtime = self._get_entrypoint_runtime()
        if current_runtime != entrypoint_runtime:
            self._update_entrypoint_runtime(deepcopy(entrypoint_runtime))
