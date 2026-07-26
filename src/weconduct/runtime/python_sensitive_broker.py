from __future__ import annotations

import json
import secrets
import socket
from threading import Event, Thread
from typing import Any

from weconduct.application.sensitive_values.models import SensitiveConsumer, SensitiveRef


_CAPABILITY_KEY = "__weconduct_sensitive_capability__"
_MAX_REQUEST_BYTES = 64 * 1024


class PythonSensitiveValueBroker:
    """为一次 python.run 子进程执行提供可撤销的本地敏感值读取能力。"""

    def __init__(self, *, sensitive_service: object, session_id: str, node_id: str) -> None:
        self._sensitive_service = sensitive_service
        self._session_id = session_id
        self._node_id = node_id
        self._capabilities: dict[str, SensitiveRef] = {}
        self._socket: socket.socket | None = None
        self._server_thread: Thread | None = None
        self._closed = Event()
        self._host = "127.0.0.1"
        self._port: int | None = None

    def __enter__(self) -> PythonSensitiveValueBroker:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def start(self) -> None:
        if self._socket is not None:
            return
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self._host, 0))
        server.listen(4)
        server.settimeout(0.1)
        self._socket = server
        self._port = int(server.getsockname()[1])
        self._server_thread = Thread(
            target=self._serve,
            name=f"weconduct-python-sensitive-broker-{self._node_id}",
            daemon=True,
        )
        self._server_thread.start()

    def close(self) -> None:
        self._closed.set()
        server, self._socket = self._socket, None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        if self._server_thread is not None:
            self._server_thread.join(timeout=1)
        self._server_thread = None
        self._capabilities.clear()
        self._port = None

    def encode_for_child(self, value: Any) -> Any:
        if isinstance(value, SensitiveRef):
            capability = secrets.token_urlsafe(32)
            self._capabilities[capability] = value
            return {_CAPABILITY_KEY: capability}
        if isinstance(value, dict):
            return {str(key): self.encode_for_child(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.encode_for_child(item) for item in value]
        if isinstance(value, tuple):
            return [self.encode_for_child(item) for item in value]
        return value

    def child_connection_config(self) -> dict[str, object] | None:
        if not self._capabilities:
            return None
        if self._port is None:
            raise RuntimeError("python sensitive broker is not started")
        return {"host": self._host, "port": self._port}

    def resolve_capability_for_test(self, encoded_value: object) -> object:
        if not isinstance(encoded_value, dict):
            raise ValueError("python sensitive capability is invalid")
        capability = encoded_value.get(_CAPABILITY_KEY)
        if not isinstance(capability, str):
            raise ValueError("python sensitive capability is invalid")
        return self._resolve_capability(capability)

    def _serve(self) -> None:
        while not self._closed.is_set():
            server = self._socket
            if server is None:
                return
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(1)
                try:
                    request = _read_json_request(connection)
                    capability = request.get("capability")
                    if not isinstance(capability, str):
                        raise ValueError("python sensitive capability is invalid")
                    response = {"ok": True, "value": _json_safe(self._resolve_capability(capability))}
                except (KeyError, PermissionError, TypeError, ValueError) as exc:
                    response = {"ok": False, "error": str(exc) or "python.sensitive_access_denied"}
                connection.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8"))

    def _resolve_capability(self, capability: str) -> object:
        ref = self._capabilities.get(capability)
        if ref is None:
            raise ValueError("python sensitive capability is unavailable")
        resolver = getattr(self._sensitive_service, "resolve", None)
        if not callable(resolver):
            raise PermissionError("python.sensitive_access_denied")
        return resolver(ref, consumer=SensitiveConsumer.RUNTIME_EXECUTOR)


def _read_json_request(connection: socket.socket) -> dict[str, object]:
    chunks: list[bytes] = []
    total = 0
    while total <= _MAX_REQUEST_BYTES:
        chunk = connection.recv(min(4096, _MAX_REQUEST_BYTES - total + 1))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total > _MAX_REQUEST_BYTES:
        raise ValueError("python sensitive request is too large")
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("python sensitive request is invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("python sensitive request is invalid")
    return payload


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return repr(value)
