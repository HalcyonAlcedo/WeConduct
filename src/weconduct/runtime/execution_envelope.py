from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, MutableMapping


class ExecutionEnvelopeError(ValueError):
    """Stable error raised when Python execution violates its declared envelope."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class FieldSchema:
    field_id: str
    value_type: str = "any"
    required: bool = False
    allow_none: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.field_id, str) or not self.field_id.strip():
            raise ExecutionEnvelopeError("python.field_id_invalid", "field_id must be a non-empty string")
        if not isinstance(self.value_type, str) or not self.value_type.strip():
            raise ExecutionEnvelopeError("python.field_schema_invalid", "value_type must be a non-empty string")


class _FieldReader:
    def __init__(self, values: Mapping[str, object]) -> None:
        self._values = values

    def get(self, field_id: str, default: object = None) -> object:
        return self._values.get(field_id, default)


class _StagedFieldWriter:
    def __init__(self, values: MutableMapping[str, object], schemas: Mapping[str, FieldSchema], *, kind: str) -> None:
        self._values = values
        self._schemas = schemas
        self._kind = kind

    def set(self, field_id: str, value: object) -> None:
        schema = self._schemas.get(field_id)
        if schema is None:
            raise ExecutionEnvelopeError(
                "python.output_undeclared" if self._kind == "output" else "python.metadata_undeclared",
                f"{self._kind} field is not declared: {field_id}",
            )
        _validate_value(schema, value)
        self._values[field_id] = value

    def get(self, field_id: str, default: object = None) -> object:
        return self._values.get(field_id, default)


class _DomainData:
    def __init__(self, values: MutableMapping[str, object], allowed_fields: frozenset[str]) -> None:
        self._values = values
        self._allowed_fields = allowed_fields

    def get(self, name: str, default: object = None) -> object:
        self._ensure_allowed(name)
        return self._values.get(name, default)

    def set(self, name: str, value: object) -> None:
        self._ensure_allowed(name)
        self._values[name] = value

    def _ensure_allowed(self, name: str) -> None:
        if name not in self._allowed_fields:
            raise ExecutionEnvelopeError("python.data_access_denied", f"data field is not available: {name}")


class _CancelFacade:
    def __init__(self, check: Callable[[], None] | None = None) -> None:
        self._check = check or (lambda: None)

    def check(self) -> None:
        self._check()


class _SessionFacade:
    def __init__(self, info: Mapping[str, object] | None = None) -> None:
        self._info = dict(info or {})

    def info(self) -> dict[str, object]:
        return dict(self._info)


@dataclass
class ExecutionContextFacade:
    inputs: _FieldReader
    outputs: _StagedFieldWriter
    metadata: _StagedFieldWriter
    data: _DomainData
    session: _SessionFacade
    cancel: _CancelFacade


@dataclass
class ExecutionEnvelope:
    inputs: Mapping[str, object]
    metadata: MutableMapping[str, object]
    output_schema: Mapping[str, FieldSchema]
    input_schema: Mapping[str, FieldSchema] = field(default_factory=dict)
    metadata_schema: Mapping[str, FieldSchema] = field(default_factory=dict)
    data_values: MutableMapping[str, object] = field(default_factory=dict)
    allowed_data_fields: frozenset[str] = frozenset()
    session_info: Mapping[str, object] = field(default_factory=dict)
    cancel_check: Callable[[], None] | None = None
    _staged_outputs: MutableMapping[str, object] = field(default_factory=dict, init=False, repr=False)
    _staged_metadata: MutableMapping[str, object] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.inputs = dict(self.inputs)
        self.metadata = dict(self.metadata)
        self.input_schema = _normalize_schema(self.input_schema)
        self.output_schema = _normalize_schema(self.output_schema)
        self.metadata_schema = _normalize_schema(self.metadata_schema)
        self.context = ExecutionContextFacade(
            inputs=_FieldReader(self.inputs),
            outputs=_StagedFieldWriter(self._staged_outputs, self.output_schema, kind="output"),
            metadata=_StagedFieldWriter(self._staged_metadata, self.metadata_schema, kind="metadata"),
            data=_DomainData(self.data_values, self.allowed_data_fields),
            session=_SessionFacade(self.session_info),
            cancel=_CancelFacade(self.cancel_check),
        )

    def commit(self) -> dict[str, dict[str, object]]:
        for field_id, schema in self.output_schema.items():
            if schema.required and field_id not in self._staged_outputs:
                raise ExecutionEnvelopeError("python.output_required", f"required output is missing: {field_id}")
        self.metadata.update(self._staged_metadata)
        return {
            "outputs": dict(self._staged_outputs),
            "metadata": dict(self.metadata),
        }

    def validate_inputs(self) -> None:
        for field_id, schema in self.input_schema.items():
            if schema.required and field_id not in self.inputs:
                raise ExecutionEnvelopeError("python.input_required", f"required input is missing: {field_id}")

    def discard(self) -> None:
        self._staged_outputs.clear()
        self._staged_metadata.clear()


def _normalize_schema(raw: Mapping[str, FieldSchema] | Mapping[str, object] | None) -> dict[str, FieldSchema]:
    if raw is None:
        return {}
    result: dict[str, FieldSchema] = {}
    for field_id, value in raw.items():
        if isinstance(value, FieldSchema):
            schema = value
        elif isinstance(value, Mapping):
            schema = FieldSchema(
                field_id=str(value.get("field_id", field_id)),
                value_type=str(value.get("type", value.get("value_type", "any"))),
                required=bool(value.get("required", False)),
                allow_none=bool(value.get("allow_none", True)),
            )
        else:
            schema = FieldSchema(field_id=str(field_id), value_type=str(value))
        result[schema.field_id] = schema
    return result


def _validate_value(schema: FieldSchema, value: object) -> None:
    if value is None:
        if schema.allow_none:
            return
        raise ExecutionEnvelopeError("python.field_type_invalid", f"field does not allow null: {schema.field_id}")
    expected = {
        "any": None,
        "object": dict,
        "list": list,
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
    }.get(schema.value_type.strip().lower())
    if expected is not None and not isinstance(value, expected):
        raise ExecutionEnvelopeError("python.field_type_invalid", f"field type is invalid: {schema.field_id}")
