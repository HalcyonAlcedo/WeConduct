from __future__ import annotations

from http import HTTPStatus
from io import BytesIO


class _ConnectionAbortedWriter:
    def write(self, _body: bytes) -> int:
        raise ConnectionAbortedError("client disconnected")

    def flush(self) -> None:
        raise ConnectionAbortedError("client disconnected")


def test_execution_event_stream_replays_terminal_event_as_sse() -> None:
    from weconduct.api.external_v1.events import ExternalExecutionEventStream

    class _Service:
        def get_runtime_stream_events_since(
            self,
            *,
            session_id: str,
            after_event_id: int | None,
        ) -> dict[str, object]:
            assert session_id == "execution-1"
            assert after_event_id == 0
            return {
                "events": [
                    {
                        "event_id": 4,
                        "event_name": "runtime.completed",
                        "payload": {"session_id": session_id, "status": "succeeded"},
                    }
                ]
            }

    class _Handler:
        def __init__(self) -> None:
            self.headers = {}
            self.wfile = BytesIO()
            self.status: int | None = None
            self.response_headers: dict[str, str] = {}
            self.close_connection = False

        def send_response(self, status: int) -> None:
            self.status = status

        def send_header(self, name: str, value: str) -> None:
            self.response_headers[name] = value

        def end_headers(self) -> None:
            pass

    handler = _Handler()

    ExternalExecutionEventStream(handler=handler, service=_Service()).write(
        execution_id="execution-1",
        request_id="request-1",
    )

    assert handler.status == HTTPStatus.OK.value
    assert handler.response_headers["Content-Type"] == "text/event-stream; charset=utf-8"
    assert handler.close_connection is True
    assert handler.wfile.getvalue().decode("utf-8") == (
        'id: 4\n'
        'event: runtime.completed\n'
        'data: {"request_id": "request-1", "result": {"session_id": "execution-1", "status": "succeeded"}}\n\n'
    )


def test_execution_event_stream_replays_terminal_event_after_subscription_closes() -> None:
    from weconduct.api.external_v1.events import ExternalExecutionEventStream

    class _Service:
        def __init__(self) -> None:
            self.replay_count = 0

        def get_runtime_stream_events_since(
            self,
            *,
            session_id: str,
            after_event_id: int | None,
        ) -> dict[str, object]:
            self.replay_count += 1
            if self.replay_count == 1:
                assert after_event_id == 0
                return {
                    "events": [
                        {
                            "event_id": 1,
                            "event_name": "runtime.snapshot",
                            "payload": {"session_id": session_id, "status": "running"},
                        }
                    ]
                }
            assert after_event_id == 1
            return {
                "events": [
                    {
                        "event_id": 2,
                        "event_name": "runtime.completed",
                        "payload": {"session_id": session_id, "status": "completed"},
                    }
                ]
            }

        def get_runtime_stream_snapshot(self, *, session_id: str) -> dict[str, object]:
            assert session_id == "execution-2"
            return {"status": "running"}

        def iter_runtime_stream_events(self, *, session_id: str, heartbeat_seconds: float):
            assert heartbeat_seconds > 0
            assert session_id == "execution-2"
            return iter(())

    class _Handler:
        def __init__(self) -> None:
            self.headers = {}
            self.wfile = BytesIO()
            self.close_connection = False

        def send_response(self, _status: int) -> None:
            pass

        def send_header(self, _name: str, _value: str) -> None:
            pass

        def end_headers(self) -> None:
            pass

    handler = _Handler()

    ExternalExecutionEventStream(handler=handler, service=_Service()).write(
        execution_id="execution-2",
        request_id="request-2",
    )

    assert "event: runtime.completed" in handler.wfile.getvalue().decode("utf-8")


def test_execution_event_stream_writes_heartbeat_as_sse_comment_without_event_id() -> None:
    from weconduct.api.external_v1.events import ExternalExecutionEventStream

    class _Service:
        def __init__(self) -> None:
            self.calls = 0

        def get_runtime_stream_events_since(
            self,
            *,
            session_id: str,
            after_event_id: int | None,
        ) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {"events": []}
            return {
                "events": [
                    {
                        "event_id": 1,
                        "event_name": "runtime.completed",
                        "payload": {"session_id": session_id, "status": "completed"},
                    }
                ]
            }

        def get_runtime_stream_snapshot(self, *, session_id: str) -> dict[str, object]:
            return {"status": "running", "session_id": session_id}

        def iter_runtime_stream_events(self, *, session_id: str, heartbeat_seconds: float):
            assert heartbeat_seconds > 0
            yield "__heartbeat__", {}
            yield "runtime.completed", {"session_id": session_id, "status": "completed"}

    class _Handler:
        def __init__(self) -> None:
            self.headers = {}
            self.wfile = BytesIO()
            self.close_connection = False

        def send_response(self, _status: int) -> None:
            pass

        def send_header(self, _name: str, _value: str) -> None:
            pass

        def end_headers(self) -> None:
            pass

    handler = _Handler()
    ExternalExecutionEventStream(handler=handler, service=_Service()).write(
        execution_id="execution-heartbeat",
        request_id="request-heartbeat",
    )

    body = handler.wfile.getvalue().decode("utf-8")
    assert ": heartbeat\n\n" in body
    assert body.index(": heartbeat\n\n") < body.index("event: runtime.completed")
    assert "id:" not in body.split(": heartbeat\n\n", 1)[0]


def test_execution_event_stream_ignores_client_connection_abort() -> None:
    from weconduct.api.external_v1.events import ExternalExecutionEventStream

    class _Service:
        def get_runtime_stream_events_since(
            self,
            *,
            session_id: str,
            after_event_id: int | None,
        ) -> dict[str, object]:
            assert session_id == "execution-abort"
            assert after_event_id == 0
            return {
                "events": [
                    {
                        "event_id": 1,
                        "event_name": "runtime.snapshot",
                        "payload": {"session_id": session_id, "status": "running"},
                    }
                ]
            }

        def get_runtime_stream_snapshot(self, *, session_id: str) -> dict[str, object]:
            return {"session_id": session_id, "status": "running"}

        def iter_runtime_stream_events(self, *, session_id: str, heartbeat_seconds: float):
            assert session_id == "execution-abort"
            assert heartbeat_seconds > 0
            yield "runtime.node", {"session_id": session_id, "node_id": "node-1"}

    class _Handler:
        def __init__(self) -> None:
            self.headers = {}
            self.wfile = _ConnectionAbortedWriter()
            self.close_connection = False

        def send_response(self, _status: int) -> None:
            pass

        def send_header(self, _name: str, _value: str) -> None:
            pass

        def end_headers(self) -> None:
            pass

    ExternalExecutionEventStream(handler=_Handler(), service=_Service()).write(
        execution_id="execution-abort",
        request_id="request-abort",
    )
