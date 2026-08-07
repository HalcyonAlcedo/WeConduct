from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from threading import Condition, RLock
from time import monotonic

from weconduct.runtime.engine import CancellationContext

from .models import (
    PendingInputRequest,
    PendingInputResult,
    PendingInputSnapshot,
    PendingInputStatus,
)


class PendingInputStateError(ValueError):
    """State conflict carrying the terminal state for API status mapping."""

    error_code = "operation.state_conflict"

    def __init__(self, message: str, *, state: PendingInputStatus) -> None:
        super().__init__(message)
        self.state = state.value


class PendingInputValidationError(ValueError):
    """Input validation failure with a safe, public error contract."""

    error_code = "operation.input_invalid"

    def __init__(self, message: str, *, details: Mapping[str, object]) -> None:
        super().__init__(message)
        self.details = dict(details)


@dataclass
class _PendingInputRecord:
    request: PendingInputRequest
    status: PendingInputStatus
    values: dict[str, object]
    deadline_monotonic: float | None


class PendingInputService:
    """Coordinates one-time, session-scoped input submissions."""

    def __init__(self, *, terminal_record_limit: int = 256) -> None:
        if (
            not isinstance(terminal_record_limit, int)
            or isinstance(terminal_record_limit, bool)
            or terminal_record_limit <= 0
        ):
            raise ValueError("terminal_record_limit must be a positive integer")
        self._condition = Condition(RLock())
        self._terminal_record_limit = terminal_record_limit
        self._records: dict[str, _PendingInputRecord] = {}

    def create(self, request: PendingInputRequest) -> PendingInputSnapshot:
        with self._condition:
            if request.request_id in self._records:
                raise ValueError("pending input request already exists")
            if any(
                record.request.execution_id == request.execution_id
                and record.status
                in {PendingInputStatus.CREATED, PendingInputStatus.WAITING}
                for record in self._records.values()
            ):
                raise ValueError("execution already has a pending input request")
            self._records[request.request_id] = _PendingInputRecord(
                request=request,
                status=PendingInputStatus.CREATED,
                values={},
                deadline_monotonic=None,
            )
            return self._snapshot(request.request_id)

    def get_snapshot(self, request_id: str) -> PendingInputSnapshot:
        with self._condition:
            return self._snapshot(request_id)

    def activate(self, request_id: str) -> PendingInputSnapshot:
        """将已创建请求置为可提交状态，再向外部发布输入提示。"""
        with self._condition:
            record = self._require_record(request_id)
            if record.status == PendingInputStatus.CREATED:
                record.status = PendingInputStatus.WAITING
                record.deadline_monotonic = (
                    monotonic() + record.request.timeout_seconds
                    if record.request.timeout_seconds > 0
                    else None
                )
            return self._snapshot(request_id)

    def get_snapshot_for_execution(self, execution_id: str) -> PendingInputSnapshot | None:
        with self._condition:
            matches = [
                request_id
                for request_id, record in self._records.items()
                if record.request.execution_id == execution_id
                and record.status
                in {PendingInputStatus.CREATED, PendingInputStatus.WAITING}
            ]
            if not matches:
                return None
            if len(matches) != 1:
                raise RuntimeError("execution has multiple pending input requests")
            return self._snapshot(matches[0])

    def wait(
        self,
        request_id: str,
        cancellation: CancellationContext,
    ) -> PendingInputResult:
        unregister = cancellation.register_cleanup(
            lambda: self._cancel_request(request_id)
        )
        try:
            with self._condition:
                record = self._require_record(request_id)
                if record.status == PendingInputStatus.CREATED:
                    self.activate(request_id)
                    record = self._require_record(request_id)
                while record.status == PendingInputStatus.WAITING:
                    wait_seconds = self._remaining_timeout(record)
                    if wait_seconds is not None and wait_seconds <= 0:
                        record.status = PendingInputStatus.TIMED_OUT
                        self._trim_terminal_records_locked()
                        break
                    self._condition.wait(timeout=wait_seconds)
                result = PendingInputResult(
                    request_id=request_id,
                    status=record.status,
                    values=dict(record.values),
                )
                record.values.clear()
                return result
        finally:
            unregister()

    def submit(
        self,
        request_id: str,
        values: Mapping[str, object],
    ) -> PendingInputSnapshot:
        with self._condition:
            record = self._require_record(request_id)
            if record.status != PendingInputStatus.WAITING:
                message = (
                    "pending input request timed out"
                    if record.status == PendingInputStatus.TIMED_OUT
                    else "pending input request is not waiting"
                )
                raise PendingInputStateError(message, state=record.status)
            normalized_values = self._validate_submission(record.request, values)
            record.values = normalized_values
            record.status = PendingInputStatus.SUBMITTED
            self._trim_terminal_records_locked()
            self._condition.notify_all()
            return self._snapshot(request_id)

    def cancel_session(self, execution_id: str) -> None:
        with self._condition:
            matching_request_ids = [
                request_id
                for request_id, record in self._records.items()
                if record.request.execution_id == execution_id
            ]
            for request_id in matching_request_ids:
                record = self._records[request_id]
                if record.status in {PendingInputStatus.CREATED, PendingInputStatus.WAITING}:
                    record.status = PendingInputStatus.CANCELLED
                record.values.clear()
            self._trim_terminal_records_locked()
            self._condition.notify_all()

    def _cancel_request(self, request_id: str) -> None:
        with self._condition:
            record = self._records.get(request_id)
            if record is not None and record.status in {
                PendingInputStatus.CREATED,
                PendingInputStatus.WAITING,
            }:
                record.status = PendingInputStatus.CANCELLED
                record.values.clear()
                self._trim_terminal_records_locked()
                self._condition.notify_all()

    def _snapshot(self, request_id: str) -> PendingInputSnapshot:
        record = self._require_record(request_id)
        return PendingInputSnapshot(
            request_id=record.request.request_id,
            execution_id=record.request.execution_id,
            node_id=record.request.node_id,
            status=record.status,
            fields=record.request.fields,
            timeout_seconds=record.request.timeout_seconds,
        )

    def _require_record(self, request_id: str) -> _PendingInputRecord:
        try:
            return self._records[request_id]
        except KeyError as exc:
            raise ValueError("pending input request was not found") from exc

    @staticmethod
    def _remaining_timeout(record: _PendingInputRecord) -> float | None:
        if record.deadline_monotonic is None:
            return None
        return record.deadline_monotonic - monotonic()

    @staticmethod
    def _validate_submission(
        request: PendingInputRequest,
        values: Mapping[str, object],
    ) -> dict[str, object]:
        if not isinstance(values, Mapping):
            raise PendingInputValidationError(
                "pending input values must be a mapping",
                details={
                    "validation_kind": "invalid_payload",
                    "expected_type": "object",
                    "actual_type": _public_value_type(values),
                },
            )
        expected_field_ids = {field.field_id for field in request.fields}
        unknown_field_ids = set(values) - expected_field_ids
        if unknown_field_ids:
            raise PendingInputValidationError(
                "pending input contains unknown fields",
                details={
                    "validation_kind": "unknown_field",
                    "field_ids": sorted(str(field_id) for field_id in unknown_field_ids),
                },
            )
        missing_required_field_ids = [
            field.field_id
            for field in request.fields
            if field.required and field.field_id not in values and not field.has_default
        ]
        if missing_required_field_ids:
            raise PendingInputValidationError(
                "pending input is missing required fields",
                details={
                    "validation_kind": "missing_required",
                    "field_ids": sorted(missing_required_field_ids),
                },
            )
        normalized: dict[str, object] = {}
        for field in request.fields:
            value = (
                values[field.field_id]
                if field.field_id in values
                else field.default_value
                if field.has_default
                else None
            )
            if value is None and not field.required:
                normalized[field.field_id] = None
                continue
            PendingInputService._validate_field_value(field, value)
            normalized[field.field_id] = value
        return normalized

    @staticmethod
    def _validate_field_value(field: object, value: object) -> None:
        field_id = getattr(field, "field_id", "field")
        value_type = str(getattr(field, "value_type", "string")).strip().lower()
        valid = (
            value_type == "any"
            or value_type in {"string", "text", "password", "secret"}
            and isinstance(value, str)
            or value_type in {"integer", "int"}
            and isinstance(value, int)
            and not isinstance(value, bool)
            or value_type in {"number", "float"}
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            or value_type in {"boolean", "bool"}
            and isinstance(value, bool)
            or value_type in {"array", "list"}
            and isinstance(value, list)
            or value_type in {"object", "map", "dict"}
            and isinstance(value, dict)
            or value_type == "json"
            and isinstance(value, (dict, list))
        )
        if valid:
            return
        expected = {
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
        }.get(value_type, value_type)
        article = "an" if expected[0] in "aeiou" else "a"
        raise PendingInputValidationError(
            f"field {field_id} must be {article} {expected}",
            details={
                "validation_kind": "type_mismatch",
                "field_id": field_id,
                "expected_type": expected,
                "actual_type": _public_value_type(value),
            },
        )

    def _trim_terminal_records_locked(self) -> None:
        terminal_request_ids = [
            request_id
            for request_id, record in self._records.items()
            if record.status
            in {
                PendingInputStatus.SUBMITTED,
                PendingInputStatus.TIMED_OUT,
                PendingInputStatus.CANCELLED,
            }
        ]
        for request_id in terminal_request_ids[: -self._terminal_record_limit]:
            self._records.pop(request_id, None)


def _public_value_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__
