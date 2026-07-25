from __future__ import annotations

from http import HTTPStatus
import json
from typing import Mapping


_TERMINAL_EVENT_NAMES = frozenset(
    {"runtime.completed", "runtime.failed", "runtime.aborted"}
)
_TERMINAL_STATUSES = frozenset({"completed", "failed", "aborted"})


class ExternalExecutionEventStream:
    """将运行时事件缓冲适配为可恢复的外部 SSE 流。"""

    def __init__(self, *, handler: object, service: object) -> None:
        self._handler = handler
        self._service = service

    def write(self, *, execution_id: str, request_id: str) -> None:
        after_event_id = self._parse_last_event_id()
        replay = self._service.get_runtime_stream_events_since(
            session_id=execution_id,
            after_event_id=after_event_id,
        )
        handler = self._handler
        handler.send_response(HTTPStatus.OK.value)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.close_connection = True
        last_event_id = after_event_id
        for event in replay["events"]:
            self._write_event(event=event, request_id=request_id)
            last_event_id = int(event["event_id"])
            if event["event_name"] in _TERMINAL_EVENT_NAMES:
                return

        snapshot = self._service.get_runtime_stream_snapshot(session_id=execution_id)
        if snapshot.get("status") in _TERMINAL_STATUSES:
            self._flush_latest_events(
                execution_id=execution_id,
                after_event_id=last_event_id,
                request_id=request_id,
            )
            return

        for _event_name, _payload in self._service.iter_runtime_stream_events(
            session_id=execution_id
        ):
            last_event_id, terminal_written = self._flush_latest_events(
                execution_id=execution_id,
                after_event_id=last_event_id,
                request_id=request_id,
            )
            if terminal_written:
                return
        self._flush_latest_events(
            execution_id=execution_id,
            after_event_id=last_event_id,
            request_id=request_id,
        )

    def _parse_last_event_id(self) -> int:
        raw_cursor = self._handler.headers.get("Last-Event-ID")
        if raw_cursor is None or not raw_cursor.strip():
            return 0
        try:
            after_event_id = int(raw_cursor.strip())
        except ValueError as exc:
            raise ValueError("execution.event_cursor_invalid") from exc
        if after_event_id < 0:
            raise ValueError("execution.event_cursor_invalid")
        return after_event_id

    def _flush_latest_events(
        self,
        *,
        execution_id: str,
        after_event_id: int,
        request_id: str,
    ) -> tuple[int, bool]:
        latest = self._service.get_runtime_stream_events_since(
            session_id=execution_id,
            after_event_id=after_event_id,
        )
        last_event_id = after_event_id
        for event in latest["events"]:
            self._write_event(event=event, request_id=request_id)
            last_event_id = int(event["event_id"])
            if event["event_name"] in _TERMINAL_EVENT_NAMES:
                return last_event_id, True
        return last_event_id, False

    def _write_event(self, *, event: Mapping[str, object], request_id: str) -> None:
        event_id = event["event_id"]
        event_name = event["event_name"]
        payload = event["payload"]
        body = (
            f"id: {event_id}\n"
            f"event: {event_name}\n"
            f"data: {json.dumps({'request_id': request_id, 'result': payload}, ensure_ascii=False)}\n\n"
        ).encode("utf-8")
        self._handler.wfile.write(body)
        self._handler.wfile.flush()
