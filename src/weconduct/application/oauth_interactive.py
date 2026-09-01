from __future__ import annotations

from dataclasses import dataclass
from threading import RLock, Thread, current_thread
from time import time
from typing import Callable, Mapping
from uuid import uuid4

from weconduct.network_runtime.oauth import (
    OAuthAuthorizationCodePKCERequest,
    OAuthConfigurationError,
    OAuthDeviceCodeState,
    OAuthService,
    OAuthTokenState,
)
from weconduct.runtime.engine import CancellationContext, RuntimeCancellationError

from .pending_input import (
    PendingInputField,
    PendingInputRequest,
    PendingInputService,
    PendingInputStatus,
)
from .pending_input.service import PendingInputStateError
from .sensitive_values import SensitiveValueService


class OAuthInteractiveError(ValueError):
    """交互式 OAuth 流程的稳定错误。"""

    def __init__(
        self,
        error_code: str,
        message: str | None = None,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.error_code = error_code
        self.details = dict(details or {})
        super().__init__(message or error_code)


@dataclass
class _OAuthFlow:
    flow_id: str
    mode: str
    scope_id: str
    oauth_service: object
    sensitive_values: SensitiveValueService
    pending_request: PendingInputRequest | None
    authorization_request: OAuthAuthorizationCodePKCERequest | None
    device_state: OAuthDeviceCodeState | None
    token_url: str
    client_id: str
    scope: str | None
    status: str
    created_at: float
    cancellation: CancellationContext
    token_state: OAuthTokenState | None = None
    error_code: str | None = None
    worker: Thread | None = None
    cleanup_requested: bool = False
    sensitive_scope_revoked: bool = False


class OAuthInteractiveService:
    """为 UI、CLI 和外部 API 提供同一套 OAuth 交互状态机。

    OAuthService 只处理协议和网络交换；本类负责将用户动作映射到
    PendingInputService，并将敏感结果限制在 flow 的内存作用域内。
    """

    def __init__(
        self,
        *,
        pending_input_service: PendingInputService | None = None,
        oauth_service_factory: Callable[[SensitiveValueService], object] | None = None,
    ) -> None:
        self._pending_input_service = pending_input_service or PendingInputService()
        self._oauth_service_factory = oauth_service_factory or (
            lambda sensitive_values: OAuthService(sensitive_values=sensitive_values)
        )
        self._lock = RLock()
        self._flows: dict[str, _OAuthFlow] = {}
        self._closed = False

    @property
    def pending_input_service(self) -> PendingInputService:
        """暴露共享待输入服务，供宿主 UI/CLI 复用同一状态源。"""
        return self._pending_input_service

    def begin_authorization_code(
        self,
        *,
        authorization_url: str,
        token_url: str,
        client_id: str,
        redirect_uri: str,
        scope: str | None = None,
        scope_id: str,
    ) -> dict[str, object]:
        self._ensure_open()
        self._require_text(scope_id, "scope_id", "oauth.scope_id_required")
        self._require_text(token_url, "token_url", "oauth.token_url_invalid")
        sensitive_values = SensitiveValueService()
        oauth_service = self._oauth_service_factory(sensitive_values)
        begin = getattr(oauth_service, "begin_authorization_code_pkce", None)
        if not callable(begin):
            raise OAuthInteractiveError("oauth.interactive_unavailable")
        request = begin(
            authorization_url=authorization_url,
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
        )
        if not isinstance(request, OAuthAuthorizationCodePKCERequest):
            raise OAuthInteractiveError("oauth.authorization_request_invalid")
        flow = self._create_flow(
            mode="authorization_code_pkce",
            scope_id=scope_id,
            oauth_service=oauth_service,
            sensitive_values=sensitive_values,
            pending_request=self._build_authorization_pending_request(),
            authorization_request=request,
            device_state=None,
            token_url=token_url,
            client_id=client_id,
            scope=scope,
        )
        self._start_worker(flow, self._run_authorization_code)
        return self._public_flow(flow)

    def begin_device_code(
        self,
        *,
        device_authorization_url: str,
        token_url: str,
        client_id: str,
        scope: str | None = None,
        scope_id: str,
    ) -> dict[str, object]:
        self._ensure_open()
        self._require_text(scope_id, "scope_id", "oauth.scope_id_required")
        self._require_text(token_url, "token_url", "oauth.token_url_invalid")
        sensitive_values = SensitiveValueService()
        oauth_service = self._oauth_service_factory(sensitive_values)
        request_device_code = getattr(oauth_service, "request_device_code", None)
        if not callable(request_device_code):
            raise OAuthInteractiveError("oauth.interactive_unavailable")
        device = request_device_code(
            device_authorization_url=device_authorization_url,
            client_id=client_id,
            scope=scope,
        )
        if not isinstance(device, OAuthDeviceCodeState):
            raise OAuthInteractiveError("oauth.device_code_state_invalid")
        flow = self._create_flow(
            mode="device_code",
            scope_id=scope_id,
            oauth_service=oauth_service,
            sensitive_values=sensitive_values,
            pending_request=self._build_device_pending_request(),
            authorization_request=None,
            device_state=device,
            token_url=token_url,
            client_id=client_id,
            scope=scope,
        )
        self._start_worker(flow, self._run_device_code)
        return self._public_flow(flow)

    def submit_flow(
        self,
        flow_id: str,
        values: Mapping[str, object],
    ) -> dict[str, object]:
        flow = self._get_flow(flow_id)
        pending = flow.pending_request
        if pending is None:
            raise OAuthInteractiveError("oauth.pending_input_unavailable")
        with self._lock:
            if flow.status in {"succeeded", "failed", "cancelled"}:
                raise OAuthInteractiveError(
                    "oauth.flow_state_conflict",
                    details={"status": flow.status},
                )
        try:
            self._pending_input_service.submit(pending.request_id, values)
        except PendingInputStateError as exc:
            error_code = (
                "oauth.flow_expired"
                if exc.state == PendingInputStatus.TIMED_OUT.value
                else "oauth.flow_cancelled"
                if exc.state == PendingInputStatus.CANCELLED.value
                else "oauth.flow_state_conflict"
            )
            raise OAuthInteractiveError(
                error_code,
                details={"state": exc.state},
            ) from exc
        except ValueError:
            raise
        with self._lock:
            if flow.status == "waiting_input":
                flow.status = "exchanging"
        return self._public_flow(flow)

    def get_flow(self, flow_id: str) -> dict[str, object]:
        return self._public_flow(self._get_flow(flow_id))

    def cancel_flow(self, flow_id: str) -> dict[str, object]:
        flow = self._get_flow(flow_id)
        with self._lock:
            if flow.status in {"succeeded", "failed", "cancelled"}:
                return self._public_flow(flow)
            flow.status = "cancelled"
            flow.error_code = "oauth.flow_cancelled"
            flow.cleanup_requested = True
        flow.cancellation.request_cancel("oauth flow cancelled")
        self._pending_input_service.cancel_session(flow.flow_id)
        self._cleanup_sensitive_scope_if_worker_stopped(flow)
        return self._public_flow(flow)

    def get_token_state(self, flow_id: str) -> OAuthTokenState | None:
        """供宿主内部把授权结果接入运行时；公开投影永远不返回 token。"""
        flow = self._get_flow(flow_id)
        with self._lock:
            return flow.token_state

    def close(self) -> None:
        with self._lock:
            self._closed = True
            flows = tuple(self._flows.values())
            for flow in flows:
                flow.cleanup_requested = True
                if flow.status not in {"succeeded", "failed", "cancelled"}:
                    flow.status = "cancelled"
                    flow.error_code = "oauth.flow_cancelled"
        for flow in flows:
            flow.cancellation.request_cancel("oauth service closed")
            self._pending_input_service.cancel_session(flow.flow_id)
        # Do not block shutdown on a provider that ignores cancellation. A worker
        # still running will perform the same cleanup in its finally block.
        for flow in flows:
            worker = flow.worker
            if worker is not None and worker.is_alive():
                worker.join(timeout=0.5)
            self._cleanup_sensitive_scope_if_worker_stopped(flow)

    def _create_flow(
        self,
        *,
        mode: str,
        scope_id: str,
        oauth_service: object,
        sensitive_values: SensitiveValueService,
        pending_request: PendingInputRequest,
        authorization_request: OAuthAuthorizationCodePKCERequest | None,
        device_state: OAuthDeviceCodeState | None,
        token_url: str,
        client_id: str,
        scope: str | None,
    ) -> _OAuthFlow:
        flow_id = f"oauth-flow-{uuid4().hex}"
        pending_request = PendingInputRequest(
            request_id=f"oauth-input-{uuid4().hex}",
            execution_id=flow_id,
            node_id=f"oauth.{mode}",
            fields=pending_request.fields,
            timeout_seconds=pending_request.timeout_seconds,
        )
        self._pending_input_service.create(pending_request)
        self._pending_input_service.activate(pending_request.request_id)
        flow = _OAuthFlow(
            flow_id=flow_id,
            mode=mode,
            scope_id=scope_id.strip(),
            oauth_service=oauth_service,
            sensitive_values=sensitive_values,
            pending_request=pending_request,
            authorization_request=authorization_request,
            device_state=device_state,
            token_url=token_url.strip(),
            client_id=client_id.strip(),
            scope=scope.strip() if isinstance(scope, str) and scope.strip() else None,
            status="waiting_input",
            created_at=time(),
            cancellation=CancellationContext(),
        )
        with self._lock:
            self._flows[flow_id] = flow
        return flow

    def _start_worker(
        self,
        flow: _OAuthFlow,
        target: Callable[[_OAuthFlow], None],
    ) -> None:
        worker = Thread(
            target=target,
            args=(flow,),
            daemon=True,
            name=f"weconduct-{flow.mode}",
        )
        flow.worker = worker
        worker.start()

    def _run_authorization_code(self, flow: _OAuthFlow) -> None:
        try:
            result = self._pending_input_service.wait(
                flow.pending_request.request_id,  # type: ignore[union-attr]
                flow.cancellation,
            )
            if result.status is not PendingInputStatus.SUBMITTED:
                self._finish_cancelled_or_failed(flow, result.status.value)
                return
            with self._lock:
                if flow.status == "cancelled":
                    return
                flow.status = "exchanging"
            exchange = getattr(flow.oauth_service, "exchange_authorization_code_pkce", None)
            if not callable(exchange):
                raise OAuthInteractiveError("oauth.interactive_unavailable")
            values = dict(result.values)
            token_state = exchange(
                request=flow.authorization_request,
                token_url=flow.token_url,
                state=values.get("state"),
                code=values.get("code"),
                nonce=values.get("nonce"),
                scope_id=flow.scope_id,
            )
            self._finish_success(flow, token_state)
        except BaseException as exc:  # noqa: BLE001 - worker boundary normalizes errors
            self._finish_error(flow, exc)
        finally:
            self._cleanup_sensitive_scope_if_worker_stopped(flow)

    def _run_device_code(self, flow: _OAuthFlow) -> None:
        try:
            result = self._pending_input_service.wait(
                flow.pending_request.request_id,  # type: ignore[union-attr]
                flow.cancellation,
            )
            if result.status is not PendingInputStatus.SUBMITTED:
                self._finish_cancelled_or_failed(flow, result.status.value)
                return
            if result.values.get("approved") is not True:
                self._finish_cancelled_or_failed(flow, "approval_rejected")
                return
            with self._lock:
                if flow.status == "cancelled":
                    return
                flow.status = "exchanging"
            exchange = getattr(flow.oauth_service, "exchange_device_code", None)
            if not callable(exchange):
                raise OAuthInteractiveError("oauth.interactive_unavailable")
            token_state = exchange(
                device=flow.device_state,
                token_url=flow.token_url,
                client_id=flow.client_id,
                scope_id=flow.scope_id,
                scope=flow.scope,
                is_cancelled=lambda: flow.cancellation.is_cancelled,
            )
            self._finish_success(flow, token_state)
        except BaseException as exc:  # noqa: BLE001 - worker boundary normalizes errors
            self._finish_error(flow, exc)
        finally:
            self._cleanup_sensitive_scope_if_worker_stopped(flow)

    def _finish_success(self, flow: _OAuthFlow, token_state: object) -> None:
        if not isinstance(token_state, OAuthTokenState):
            self._finish_error(flow, OAuthInteractiveError("oauth.token_response_invalid"))
            return
        with self._lock:
            if flow.status == "cancelled":
                return
            flow.token_state = token_state
            flow.status = "succeeded"
            flow.error_code = None

    def _finish_cancelled_or_failed(self, flow: _OAuthFlow, reason: str) -> None:
        with self._lock:
            if flow.status == "cancelled":
                return
            flow.status = "cancelled" if reason in {"cancelled", "timed_out"} else "failed"
            flow.error_code = (
                "oauth.flow_cancelled"
                if flow.status == "cancelled"
                else "oauth.pending_input_rejected"
            )

    def _finish_error(self, flow: _OAuthFlow, error: BaseException) -> None:
        if isinstance(error, (RuntimeCancellationError, OAuthInteractiveError)):
            error_code = (
                error.error_code
                if isinstance(error, OAuthInteractiveError)
                else "oauth.flow_cancelled"
            )
        elif isinstance(error, OAuthConfigurationError):
            error_code = str(error) or "oauth.interactive_failed"
        elif isinstance(error, ValueError):
            error_code = str(error) if str(error).startswith("oauth.") else "oauth.interactive_failed"
        else:
            error_code = "oauth.interactive_failed"
        with self._lock:
            if flow.status == "cancelled":
                return
            flow.status = "cancelled" if error_code == "oauth.flow_cancelled" else "failed"
            flow.error_code = error_code

    def _get_flow(self, flow_id: str) -> _OAuthFlow:
        if not isinstance(flow_id, str) or not flow_id.strip():
            raise OAuthInteractiveError("oauth.flow_id_required")
        with self._lock:
            flow = self._flows.get(flow_id.strip())
        if flow is None:
            raise OAuthInteractiveError("oauth.flow_not_found")
        return flow

    def _ensure_open(self) -> None:
        with self._lock:
            if self._closed:
                raise OAuthInteractiveError("oauth.service_closed")

    def _cleanup_sensitive_scope_if_worker_stopped(self, flow: _OAuthFlow) -> None:
        with self._lock:
            if not flow.cleanup_requested or flow.sensitive_scope_revoked:
                return
            worker = flow.worker
            if worker is not None and worker.is_alive() and worker is not current_thread():
                return
            flow.sensitive_scope_revoked = True
        flow.sensitive_values.revoke_scope(flow.scope_id)

    def _public_flow(self, flow: _OAuthFlow) -> dict[str, object]:
        pending: dict[str, object] | None = None
        if flow.pending_request is not None:
            try:
                pending = _public_pending_input_snapshot(
                    self._pending_input_service.get_snapshot(flow.pending_request.request_id)
                )
            except ValueError:
                pending = None
        result: dict[str, object] = {
            "flow_id": flow.flow_id,
            "flow_type": flow.mode,
            "status": flow.status,
            "scope_id": flow.scope_id,
            "request_id": flow.pending_request.request_id if flow.pending_request else None,
            "pending_input": pending,
            "created_at": flow.created_at,
            "error_code": flow.error_code,
        }
        if flow.authorization_request is not None:
            result.update(
                {
                    "authorization_url": flow.authorization_request.authorization_url,
                    "redirect_uri": flow.authorization_request.redirect_uri,
                }
            )
        if flow.device_state is not None:
            result.update(
                {
                    "verification_uri": flow.device_state.verification_uri,
                    "user_code": flow.device_state.user_code,
                    "expires_at": flow.device_state.expires_at,
                    "interval": flow.device_state.interval,
                }
            )
        token_state = flow.token_state
        if token_state is not None:
            result.update(
                {
                    "token_type": token_state.token_type,
                    "token_expires_at": token_state.expires_at,
                }
            )
        return result

    @staticmethod
    def _build_authorization_pending_request() -> PendingInputRequest:
        return PendingInputRequest(
            request_id="placeholder",
            execution_id="placeholder",
            node_id="oauth.authorization_code_pkce",
            fields=(
                PendingInputField(
                    field_id="code",
                    label="OAuth authorization code",
                    sensitive=True,
                ),
                PendingInputField(
                    field_id="state",
                    label="OAuth state",
                    sensitive=True,
                ),
                PendingInputField(
                    field_id="nonce",
                    label="OAuth nonce",
                    sensitive=True,
                ),
            ),
        )

    @staticmethod
    def _build_device_pending_request() -> PendingInputRequest:
        return PendingInputRequest(
            request_id="placeholder",
            execution_id="placeholder",
            node_id="oauth.device_code",
            fields=(
                PendingInputField(
                    field_id="approved",
                    label="Device authorization completed",
                    value_type="boolean",
                ),
            ),
        )

    @staticmethod
    def _require_text(value: object, field_name: str, error_code: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise OAuthInteractiveError(error_code, details={"field": field_name})
        return value.strip()


def _public_pending_input_snapshot(snapshot: object) -> dict[str, object]:
    fields = []
    for field in getattr(snapshot, "fields", ()):
        fields.append(
            {
                "field_id": field.field_id,
                "label": field.label,
                "value_type": field.value_type,
                "required": field.required,
                "sensitive": field.sensitive,
            }
        )
    status = getattr(snapshot, "status", None)
    return {
        "request_id": getattr(snapshot, "request_id", None),
        "execution_id": getattr(snapshot, "execution_id", None),
        "status": getattr(status, "value", status),
        "fields": fields,
        "timeout_seconds": getattr(snapshot, "timeout_seconds", None),
    }


__all__ = ["OAuthInteractiveError", "OAuthInteractiveService"]
