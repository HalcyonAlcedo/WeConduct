from __future__ import annotations

from hashlib import sha256
from http import HTTPStatus
import json
from typing import Callable, Mapping
from urllib.parse import urlparse
import uuid

from weconduct.application.operations import HostOperationService, OperationRegistryError

from .auth import ExternalApiAuthenticator


def resolve_external_operation(
    *,
    method: str,
    request_path: str,
    read_payload: Callable[[], dict[str, object]] | None = None,
) -> tuple[str, dict[str, object]]:
    """将固定 v1 HTTP 路径映射到唯一的稳定 operation_id。"""

    read = read_payload or (lambda: {})
    if method == "GET":
        static_routes = {
            "/api/ext/v1/host": ("host.describe", {}),
            "/api/ext/v1/host/capabilities": ("host.capabilities", {}),
            "/api/ext/v1/project/current": ("project.current.get", {}),
            "/api/ext/v1/graph": ("graph.get", {}),
        }
        if request_path in static_routes:
            return static_routes[request_path]
    if method == "POST":
        operation_by_path = {
            "/api/ext/v1/projects": "project.create",
            "/api/ext/v1/project/open": "project.open",
            "/api/ext/v1/project/save": "project.save",
            "/api/ext/v1/project/close": "project.close",
            "/api/ext/v1/graph/validate": "graph.validate",
            "/api/ext/v1/graph/compile": "graph.compile",
            "/api/ext/v1/graph/node-drafts": "graph.node_draft.build",
            "/api/ext/v1/executions": "execution.start",
        }
        operation_id = operation_by_path.get(request_path)
        if operation_id is not None:
            return operation_id, dict(read())
    if method == "PUT" and request_path == "/api/ext/v1/graph":
        return "graph.replace", dict(read())
    prefix = "/api/ext/v1/executions/"
    if request_path.startswith(prefix):
        parts = [item for item in request_path[len(prefix):].split("/") if item]
        if len(parts) == 1 and method == "GET":
            return "execution.get", {"execution_id": parts[0]}
        if len(parts) == 2 and parts[1] == "cancel" and method == "POST":
            payload = dict(read())
            payload["execution_id"] = parts[0]
            return "execution.cancel", payload
        if len(parts) == 2 and parts[1] == "events" and method == "GET":
            return "execution.events.subscribe", {"execution_id": parts[0]}
        if len(parts) == 2 and parts[1] == "pending-input" and method == "GET":
            return "pending_input.get", {"execution_id": parts[0]}
        if len(parts) == 4 and parts[1] == "pending-input" and parts[3] == "submit" and method == "POST":
            payload = dict(read())
            payload["execution_id"] = parts[0]
            payload["request_id"] = parts[2]
            return "pending_input.submit", payload
    raise OperationRegistryError("operation.not_found", f"external route not found: {method} {request_path}")


class ExternalV1Router:
    """外部 v1 的薄 HTTP adapter；业务操作仅通过 HostOperationService 调用。"""

    def __init__(self, handler: object) -> None:
        self._handler = handler

    def handle(self, *, method: str) -> bool:
        handler = self._handler
        request_path = urlparse(handler.path).path
        if not request_path.startswith("/api/ext/v1"):
            return False
        if not getattr(handler.server, "external_api_enabled", False):
            handler._write_json(HTTPStatus.NOT_FOUND, {"error_code": "external_api.disabled", "message": "external API is disabled"})
            return True
        authenticator = ExternalApiAuthenticator(getattr(handler.server, "external_api_token", None))
        if not authenticator.accepts(handler.headers.get("Authorization", "")):
            handler._write_json(HTTPStatus.UNAUTHORIZED, {"error_code": "external_api.unauthorized", "message": "valid bearer token is required"})
            return True

        payload: dict[str, object] = {}
        idempotency_cache_key: str | None = None
        service = None
        try:
            service = handler._get_service()
            operation_service = HostOperationService(
                service=service,
                host_metadata={"instance_id": handler.server.external_api_instance_id},
                project_path_allowed_roots=getattr(
                    handler.server,
                    "external_api_project_allowed_roots",
                    (),
                ),
            )
            request_id = handler.headers.get("X-Request-ID") or f"request-{uuid.uuid4().hex[:12]}"
            operation_id, payload = resolve_external_operation(
                method=method,
                request_path=request_path,
                read_payload=self._read_optional_json_body_or_empty,
            )
            if operation_id == "execution.events.subscribe":
                self._write_execution_events(service=service, execution_id=payload["execution_id"], request_id=request_id)
                return True
            descriptor = operation_service.describe(operation_id)
            idempotency_cache_key = self._get_idempotency_cache_key(operation_id=operation_id, enabled=descriptor.idempotency_capability)
            if operation_id == "project.save" and idempotency_cache_key is None:
                raise OperationRegistryError(
                    "operation.idempotency_key_required",
                    "Idempotency-Key is required for project.save",
                    operation_id=operation_id,
                )
            if idempotency_cache_key is not None:
                replay = handler.server.begin_external_idempotency(idempotency_cache_key)
                if replay is not None:
                    state, status_value, cached_payload = replay
                    if state == "in_progress":
                        handler._write_json(HTTPStatus.CONFLICT, {"error_code": "operation.in_progress", "message": "an identical operation is already in progress", "request_id": request_id, "operation_id": operation_id})
                    else:
                        handler._write_json(HTTPStatus(status_value), cached_payload)
                    return True
            result = operation_service.execute(operation_id, payload)
            response_status = HTTPStatus.ACCEPTED if operation_id in {"execution.start", "pending_input.submit"} else HTTPStatus.OK
            response_payload = {"operation_id": operation_id, "contract_version": descriptor.contract_version, "request_id": request_id, "result": result}
            if idempotency_cache_key is not None:
                handler.server.complete_external_idempotency(idempotency_cache_key, status=response_status, payload=response_payload)
            handler._write_json(response_status, response_payload)
        except OperationRegistryError as exc:
            status = {
                "operation.not_found": HTTPStatus.NOT_FOUND,
                "operation.input_invalid": HTTPStatus.UNPROCESSABLE_ENTITY,
                "operation.path_denied": HTTPStatus.FORBIDDEN,
                "operation.state_conflict": HTTPStatus.CONFLICT,
                "graph.revision_conflict": HTTPStatus.CONFLICT,
                "operation.idempotency_key_required": HTTPStatus.PRECONDITION_REQUIRED,
                "operation.not_available": HTTPStatus.NOT_IMPLEMENTED,
            }.get(exc.error_code, HTTPStatus.INTERNAL_SERVER_ERROR)
            if exc.error_code == "operation.state_conflict" and exc.details.get("state") == "timed_out":
                status = HTTPStatus.GONE
            response_payload = {"error_code": exc.error_code, "message": str(exc), "details": dict(exc.details), "request_id": handler.headers.get("X-Request-ID"), "operation_id": exc.operation_id}
            if idempotency_cache_key is not None:
                handler.server.complete_external_idempotency(idempotency_cache_key, status=status, payload=response_payload)
            handler._write_json(status, response_payload)
        except ValueError as exc:
            error_code = str(exc) if str(exc).startswith("execution.") else "operation.input_invalid"
            status = HTTPStatus.CONFLICT if str(exc) == "execution.event_cursor_expired" else HTTPStatus.UNPROCESSABLE_ENTITY
            details: dict[str, object] = {}
            if str(exc) == "execution.event_cursor_expired" and service is not None:
                execution_id = payload.get("execution_id")
                if isinstance(execution_id, str):
                    try:
                        replay = service.get_runtime_stream_events_since(session_id=execution_id, after_event_id=None)
                        details = {"oldest_event_id": replay.get("oldest_event_id"), "latest_event_id": replay.get("latest_event_id")}
                    except (ValueError, KeyError):
                        details = {}
            response_payload = {"error_code": error_code, "message": str(exc), "details": details, "request_id": handler.headers.get("X-Request-ID")}
            if idempotency_cache_key is not None:
                handler.server.complete_external_idempotency(idempotency_cache_key, status=status, payload=response_payload)
            handler._write_json(status, response_payload)
        return True

    def _read_optional_json_body_or_empty(self) -> dict[str, object]:
        payload = self._handler._read_optional_json_request_body()
        return payload if isinstance(payload, dict) else {}

    def _get_idempotency_cache_key(self, *, operation_id: str, enabled: bool) -> str | None:
        if not enabled:
            return None
        raw_key = self._handler.headers.get("Idempotency-Key")
        if not isinstance(raw_key, str) or not (idempotency_key := raw_key.strip()):
            return None
        _, _, caller_token = self._handler.headers.get("Authorization", "").partition(" ")
        if not caller_token:
            return None
        return f"{sha256(caller_token.encode('utf-8')).hexdigest()}:{operation_id}:{idempotency_key}"

    def _write_execution_events(self, *, service: object, execution_id: object, request_id: str) -> None:
        if not isinstance(execution_id, str):
            raise ValueError("execution.event_cursor_invalid")
        raw_cursor = self._handler.headers.get("Last-Event-ID")
        if raw_cursor is None or not raw_cursor.strip():
            after_event_id = 0
        else:
            try:
                after_event_id = int(raw_cursor.strip())
            except ValueError as exc:
                raise ValueError("execution.event_cursor_invalid") from exc
            if after_event_id < 0:
                raise ValueError("execution.event_cursor_invalid")
        replay = service.get_runtime_stream_events_since(session_id=execution_id, after_event_id=after_event_id)
        handler = self._handler
        handler.send_response(HTTPStatus.OK.value)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.close_connection = True
        last_event_id = after_event_id
        for event in replay["events"]:
            self._write_sse_event(event_id=str(event["event_id"]), event_name=event["event_name"], payload={"request_id": request_id, "result": event["payload"]})
            last_event_id = int(event["event_id"])
            if event["event_name"] in {"runtime.completed", "runtime.failed", "runtime.aborted"}:
                break
        else:
            snapshot = service.get_runtime_stream_snapshot(session_id=execution_id)
            if snapshot.get("status") in {"completed", "failed", "aborted"}:
                latest = service.get_runtime_stream_events_since(session_id=execution_id, after_event_id=last_event_id)
                for event in latest["events"]:
                    self._write_sse_event(event_id=str(event["event_id"]), event_name=event["event_name"], payload={"request_id": request_id, "result": event["payload"]})
                return
            for _event_name, _payload in service.iter_runtime_stream_events(session_id=execution_id):
                replayed = service.get_runtime_stream_events_since(session_id=execution_id, after_event_id=last_event_id)
                for event in replayed["events"]:
                    self._write_sse_event(event_id=str(event["event_id"]), event_name=event["event_name"], payload={"request_id": request_id, "result": event["payload"]})
                    last_event_id = int(event["event_id"])
                    if event["event_name"] in {"runtime.completed", "runtime.failed", "runtime.aborted"}:
                        return

    def _write_sse_event(self, *, event_id: str, event_name: str, payload: Mapping[str, object]) -> None:
        body = f"id: {event_id}\nevent: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        self._handler.wfile.write(body)
        self._handler.wfile.flush()
