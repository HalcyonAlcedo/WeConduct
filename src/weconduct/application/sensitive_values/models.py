from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic_core import core_schema


class SensitiveConsumer(StrEnum):
    NETWORK_RUNTIME = "network_runtime"
    RUNTIME_EXECUTOR = "runtime_executor"
    OPERATION_BROKER = "operation_broker"


@dataclass(frozen=True, repr=False)
class SensitiveRef:
    ref_id: str
    scope_id: str
    source: Literal[
        "runtime_input",
        "encrypted_parameter",
        "plaintext_literal",
        "derived",
    ]

    def __repr__(self) -> str:
        return "SensitiveRef(<redacted>)"

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: object,
        handler: object,
    ) -> core_schema.CoreSchema:
        del source_type, handler
        return core_schema.is_instance_schema(
            cls,
            serialization=core_schema.plain_serializer_function_ser_schema(
                _reject_sensitive_ref_serialization,
            ),
        )


def _reject_sensitive_ref_serialization(value: SensitiveRef) -> Any:
    del value
    raise TypeError("SensitiveRef cannot be serialized")
