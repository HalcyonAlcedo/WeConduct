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


@dataclass
class _PendingInputRecord:
    request: PendingInputRequest
    status: PendingInputStatus
    values: dict[str, object]
    deadline_monotonic: float | None


class PendingInputService:
    """Coordinates one-time, session-scoped input submissions."""

    def __init__(self) -> None:
        self._condition = Condition(RLock())
        self._records: dict[str, _PendingInputRecord] = {}

    def create(self, request: PendingInputRequest) -> PendingInputSnapshot:
        with self._condition:
            if request.request_id in self._records:
                raise ValueError("pending input request already exists")
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

    def get_snapshot_for_execution(self, execution_id: str) -> PendingInputSnapshot | None:
        with self._condition:
            matches = [
                request_id
                for request_id, record in self._records.items()
                if record.request.execution_id == execution_id
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
                    record.status = PendingInputStatus.WAITING
                    record.deadline_monotonic = (
                        monotonic() + record.request.timeout_seconds
                        if record.request.timeout_seconds > 0
                        else None
                    )
                while record.status == PendingInputStatus.WAITING:
                    wait_seconds = self._remaining_timeout(record)
                    if wait_seconds is not None and wait_seconds <= 0:
                        record.status = PendingInputStatus.TIMED_OUT
                        break
                    self._condition.wait(timeout=wait_seconds)
                return PendingInputResult(
                    request_id=request_id,
                    status=record.status,
                    values=dict(record.values),
                )
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
                if record.status == PendingInputStatus.TIMED_OUT:
                    raise PendingInputStateError(
                        "pending input request timed out",
                        state=record.status,
                    )
                raise ValueError("pending input request is not waiting")
            normalized_values = self._validate_submission(record.request, values)
            record.values = normalized_values
            record.status = PendingInputStatus.SUBMITTED
            self._condition.notify_all()
            return self._snapshot(request_id)

    def cancel_session(self, execution_id: str) -> None:
        with self._condition:
            for record in self._records.values():
                if (
                    record.request.execution_id == execution_id
                    and record.status in {PendingInputStatus.CREATED, PendingInputStatus.WAITING}
                ):
                    record.status = PendingInputStatus.CANCELLED
            self._condition.notify_all()

    def _cancel_request(self, request_id: str) -> None:
        with self._condition:
            record = self._records.get(request_id)
            if record is not None and record.status in {
                PendingInputStatus.CREATED,
                PendingInputStatus.WAITING,
            }:
                record.status = PendingInputStatus.CANCELLED
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
            raise ValueError("pending input values must be a mapping")
        expected_field_ids = {field.field_id for field in request.fields}
        unknown_field_ids = set(values) - expected_field_ids
        if unknown_field_ids:
            raise ValueError("pending input contains unknown fields")
        missing_required_field_ids = [
            field.field_id
            for field in request.fields
            if field.required and field.field_id not in values and not field.has_default
        ]
        if missing_required_field_ids:
            raise ValueError("pending input is missing required fields")
        return {
            field.field_id: (
                values[field.field_id]
                if field.field_id in values
                else field.default_value
                if field.has_default
                else None
            )
            for field in request.fields
        }
