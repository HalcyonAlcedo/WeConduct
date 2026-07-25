from __future__ import annotations

from http import HTTPStatus
from io import BytesIO


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

        def iter_runtime_stream_events(self, *, session_id: str):
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
