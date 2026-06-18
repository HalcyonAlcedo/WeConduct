from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import json
from pathlib import Path
import threading
from typing import Protocol

WORKSPACE_STATE_VERSION = 1


class WorkspaceStateStore(Protocol):
    def load(self) -> dict | None:
        ...

    def save(self, state: dict) -> None:
        ...

    def mutate(self, mutation: Callable[[dict | None], dict]) -> dict:
        ...


class InMemoryWorkspaceStateStore:
    def __init__(self, initial_state: dict | None = None) -> None:
        self._state = deepcopy(initial_state) if initial_state is not None else None
        self._lock = threading.RLock()

    def load(self) -> dict | None:
        with self._lock:
            if self._state is None:
                return None
            return deepcopy(self._state)

    def save(self, state: dict) -> None:
        with self._lock:
            self._state = deepcopy(state)

    def mutate(self, mutation: Callable[[dict | None], dict]) -> dict:
        with self._lock:
            next_state = mutation(deepcopy(self._state) if self._state is not None else None)
            self._state = deepcopy(next_state)
            return deepcopy(self._state)


class FileWorkspaceStateStore:
    _path_locks: dict[str, threading.RLock] = {}
    _path_locks_guard = threading.Lock()

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> dict | None:
        with self._acquire_path_lock():
            return self._load_unlocked()

    def save(self, state: dict) -> None:
        with self._acquire_path_lock():
            self._save_unlocked(state)

    def mutate(self, mutation: Callable[[dict | None], dict]) -> dict:
        with self._acquire_path_lock():
            next_state = mutation(self._load_unlocked())
            self._save_unlocked(next_state)
            return deepcopy(next_state)

    def _load_unlocked(self) -> dict | None:
        if not self._path.exists():
            return None
        try:
            state = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("workspace state file must be valid JSON") from exc
        self._validate_state(state)
        return state

    def _save_unlocked(self, state: dict) -> None:
        self._validate_state(state)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self._path)

    def _acquire_path_lock(self) -> threading.RLock:
        path_key = str(self._path.resolve())
        with self._path_locks_guard:
            lock = self._path_locks.get(path_key)
            if lock is None:
                lock = threading.RLock()
                self._path_locks[path_key] = lock
        return lock

    def _validate_state(self, state: dict) -> None:
        if not isinstance(state, dict):
            raise ValueError("workspace state must be a JSON object")
        required_keys = {
            "workspace_state_version",
            "workbench",
            "last_compile",
            "compile_history",
        }
        for key in required_keys:
            if key not in state:
                raise ValueError(f"workspace state missing required key: {key}")
        if state["workspace_state_version"] != WORKSPACE_STATE_VERSION:
            raise ValueError(
                "workspace state version mismatch: "
                f"expected {WORKSPACE_STATE_VERSION}, got {state['workspace_state_version']}"
            )
