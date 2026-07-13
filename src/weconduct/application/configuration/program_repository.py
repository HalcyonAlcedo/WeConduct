from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path


PROGRAM_CONFIGURATION_FORMAT_VERSION = 1


class FileProgramConfigurationRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict:
        payload = self._read_payload()
        if not self.is_current_payload(payload):
            return {}
        values = payload.get("values")
        return deepcopy(values) if isinstance(values, dict) else {}

    def save(self, payload: dict) -> None:
        document = {
            "configuration_format_version": PROGRAM_CONFIGURATION_FORMAT_VERSION,
            "scope": "program",
            "values": deepcopy(payload),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(f".{self.path.name}.tmp")
        temporary_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)

    def read_legacy_payload(self) -> dict:
        payload = self._read_payload()
        return deepcopy(payload) if isinstance(payload, dict) else {}

    def is_current(self) -> bool:
        return self.is_current_payload(self._read_payload())

    def backup_legacy_file(self) -> Path | None:
        if not self.path.exists():
            return None
        backup_path = self.path.with_suffix(".json.0.8.0.bak")
        if not backup_path.exists():
            backup_path.write_bytes(self.path.read_bytes())
        return backup_path

    @staticmethod
    def is_current_payload(payload: object) -> bool:
        return (
            isinstance(payload, dict)
            and payload.get("configuration_format_version") == PROGRAM_CONFIGURATION_FORMAT_VERSION
            and payload.get("scope") == "program"
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
