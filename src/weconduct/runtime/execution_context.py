from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExecutionTokenContext:
    """Non-sensitive execution state that follows one control-flow token."""

    network_context_id: str | None = None
    network_context_epoch: int | None = None

    def to_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        if self.network_context_id is not None:
            snapshot["network_context_id"] = self.network_context_id
        if self.network_context_epoch is not None:
            snapshot["network_context_epoch"] = self.network_context_epoch
        return snapshot

    @classmethod
    def from_snapshot(cls, snapshot: object) -> ExecutionTokenContext:
        if not isinstance(snapshot, dict):
            return cls()
        raw_context_id = snapshot.get("network_context_id")
        raw_epoch = snapshot.get("network_context_epoch")
        if not isinstance(raw_context_id, str) or not raw_context_id.strip():
            return cls()
        epoch = (
            raw_epoch
            if isinstance(raw_epoch, int) and not isinstance(raw_epoch, bool) and raw_epoch >= 0
            else None
        )
        return cls(
            network_context_id=raw_context_id.strip(),
            network_context_epoch=epoch,
        )


@dataclass
class ExecutionSessionContext:
    """Execution-wide state shared by the runtime context compatibility facade."""

    session_id: str
    token_context: ExecutionTokenContext = field(default_factory=ExecutionTokenContext)
    cancellation_context: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        self.session_id = self.session_id.strip()
        if not isinstance(self.token_context, ExecutionTokenContext):
            self.token_context = ExecutionTokenContext()
