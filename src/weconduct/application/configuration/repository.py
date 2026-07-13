from __future__ import annotations

from copy import deepcopy
from typing import Protocol


class ConfigurationRepository(Protocol):
    def load(self) -> dict:
        ...

    def save(self, payload: dict) -> None:
        ...


class InMemoryConfigurationRepository:
    def __init__(self, initial_payload: dict | None = None) -> None:
        self._payload = deepcopy(initial_payload) if isinstance(initial_payload, dict) else {}

    def load(self) -> dict:
        return deepcopy(self._payload)

    def save(self, payload: dict) -> None:
        self._payload = deepcopy(payload)
