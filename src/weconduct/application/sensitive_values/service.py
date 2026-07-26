from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal
from uuid import uuid4

from .models import SensitiveConsumer, SensitiveRef
from .encryption import decrypt_parameter_values


_SENSITIVE_SOURCES = {
    "runtime_input",
    "encrypted_parameter",
    "plaintext_literal",
    "derived",
}


class SensitiveValueService:
    """Stores sensitive values only for the active execution scope."""

    def __init__(self) -> None:
        self._values_by_ref_id: dict[str, object] = {}
        self._refs_by_scope_id: dict[str, set[str]] = {}

    def create(
        self,
        value: object,
        *,
        scope_id: str,
        source: Literal[
            "runtime_input",
            "encrypted_parameter",
            "plaintext_literal",
            "derived",
        ],
    ) -> SensitiveRef:
        if not isinstance(scope_id, str) or not scope_id.strip():
            raise ValueError("scope_id must be a non-empty string")
        if source not in _SENSITIVE_SOURCES:
            raise ValueError("unsupported sensitive value source")
        ref = SensitiveRef(
            ref_id=uuid4().hex,
            scope_id=scope_id.strip(),
            source=source,
        )
        self._values_by_ref_id[ref.ref_id] = value
        self._refs_by_scope_id.setdefault(ref.scope_id, set()).add(ref.ref_id)
        return ref

    def derive(self, value: object, *, parents: Sequence[SensitiveRef]) -> SensitiveRef:
        if not parents:
            raise ValueError("derived sensitive values require at least one parent")
        scope_ids = {parent.scope_id for parent in parents if isinstance(parent, SensitiveRef)}
        if len(scope_ids) != 1 or len(scope_ids) != len({parent.scope_id for parent in parents}):
            raise ValueError("derived sensitive values require one shared scope")
        for parent in parents:
            self._resolve_ref(parent)
        return self.create(value, scope_id=next(iter(scope_ids)), source="derived")

    def resolve(self, ref: SensitiveRef, *, consumer: SensitiveConsumer) -> object:
        if not isinstance(consumer, SensitiveConsumer):
            raise PermissionError("sensitive consumer is not declared")
        return self._resolve_ref(ref)

    def revoke_scope(self, scope_id: str) -> None:
        for ref_id in self._refs_by_scope_id.pop(scope_id, set()):
            self._values_by_ref_id.pop(ref_id, None)

    def values_for_scope(self, scope_id: str) -> tuple[object, ...]:
        """返回仅供运行时公开投影遮罩使用的会话内原始值。"""
        return tuple(
            self._values_by_ref_id[ref_id]
            for ref_id in self._refs_by_scope_id.get(scope_id, set())
            if ref_id in self._values_by_ref_id
        )

    def unlock_encrypted_parameters(
        self,
        envelope: Mapping[str, object],
        *,
        password: str,
        scope_id: str,
    ) -> dict[str, SensitiveRef]:
        values = decrypt_parameter_values(envelope, password=password)
        return {
            name: self.create(
                value,
                scope_id=scope_id,
                source="encrypted_parameter",
            )
            for name, value in values.items()
            if isinstance(name, str)
        }

    def _resolve_ref(self, ref: SensitiveRef) -> object:
        if not isinstance(ref, SensitiveRef):
            raise TypeError("expected SensitiveRef")
        try:
            return self._values_by_ref_id[ref.ref_id]
        except KeyError as exc:
            raise KeyError("sensitive value reference is unavailable") from exc
