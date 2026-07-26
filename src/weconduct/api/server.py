import json
import ipaddress
import mimetypes
from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
from threading import Condition, RLock
from typing import Callable, TypeVar
from urllib.parse import parse_qs, unquote, urlparse
import uuid

from weconduct.application import (
    CompilationWorkbenchService,
    FileWorkspaceStateStore,
    GraphDocumentRevisionConflictError,
    UpdateService,
)
from weconduct.application.configuration import (
    ConfigurationService,
    HighRiskConfigurationChangeRequiredError,
)
from weconduct.application.configuration.builtin_registry import (
    build_builtin_configuration_registry,
)
from weconduct.application.configuration.migration import migrate_program_configuration
from weconduct.application.configuration.migration import migrate_graph_configuration
from weconduct.application.configuration.graph_repository import (
    FileGraphConfigurationRepository,
    WorkbenchGraphConfigurationRepository,
)
from weconduct.application.configuration.project_repository import ProjectConfigurationRepository
from weconduct.application.configuration.program_repository import (
    FileProgramConfigurationRepository,
)
from weconduct.application.compilation_workbench_service import (
    DIAGNOSTIC_SEVERITIES,
    DIAGNOSTIC_SEVERITY_RANK,
    ProjectPythonRuntimeExportError,
)
from weconduct.application.operations import (
    InMemoryOperationAuditTrail,
    InMemoryOperationIdempotencyStore,
)
from weconduct.api.external_v1 import ExternalV1Router

DEFAULT_WORKSPACE_STATE_PATH = (
    Path(__file__).resolve().parents[3] / ".weconduct" / "workspace-state.json"
)
DEFAULT_PREFERENCES_PATH = Path(__file__).resolve().parents[3] / ".weconduct" / "preferences.json"
DEFAULT_UI_DIST_PATH = Path(__file__).resolve().parents[3] / "ui" / "dist"
EXTERNAL_IDEMPOTENCY_CACHE_LIMIT = 256
DebugActionResult = TypeVar("DebugActionResult")


def _public_pending_input_snapshot(snapshot: object) -> dict[str, object]:
    if snapshot is None:
        return {"status": "none"}
    if isinstance(snapshot, dict):
        source = snapshot
    else:
        source = {
            "execution_id": getattr(snapshot, "execution_id", None),
            "request_id": getattr(snapshot, "request_id", None),
            "status": getattr(snapshot, "status", None),
            "fields": getattr(snapshot, "fields", ()),
            "timeout_seconds": getattr(snapshot, "timeout_seconds", None),
        }
    fields: list[dict[str, object]] = []
    for field in source.get("fields", ()):
        if isinstance(field, dict):
            field_id = field.get("field_id")
            label = field.get("label")
            value_type = field.get("value_type", field.get("type", "string"))
            sensitive = field.get("sensitive", False)
            required = field.get("required", True)
        else:
            field_id = getattr(field, "field_id", None)
            label = getattr(field, "label", None)
            value_type = getattr(field, "value_type", "string")
            sensitive = getattr(field, "sensitive", False)
            required = getattr(field, "required", True)
        if isinstance(field_id, str) and isinstance(label, str):
            fields.append(
                {
                    "field_id": field_id,
                    "label": label,
                    "value_type": value_type,
                    "sensitive": bool(sensitive),
                    "required": bool(required),
                }
            )
    status = source.get("status")
    return {
        "execution_id": source.get("execution_id"),
        "request_id": source.get("request_id"),
        "status": getattr(status, "value", status),
        "fields": fields,
        "timeout_seconds": source.get("timeout_seconds"),
    }


def _validate_external_api_bind_host(
    host: str,
    *,
    allow_non_loopback: bool,
) -> None:
    """拒绝未明确确认的外部 API 非回环监听地址。"""
    normalized_host = host.strip().lower()
    if normalized_host == "localhost":
        return

    try:
        is_loopback = ipaddress.ip_address(normalized_host).is_loopback
    except ValueError:
        is_loopback = False

    if not is_loopback and not allow_non_loopback:
        raise ValueError(
            "external_api.non_loopback_confirmation_required: "
            "set allow_non_loopback=True only after reviewing the bind address and firewall exposure"
        )


def _load_external_api_program_configuration(preferences_path: Path) -> dict[str, object]:
    configuration_service = ConfigurationService(
        registry=build_builtin_configuration_registry(),
        repositories={"program": FileProgramConfigurationRepository(preferences_path)},
    )
    values = configuration_service.get_values(scope="program")["values"]
    security = values.get("security", {})
    if not isinstance(security, dict):
        return {
            "enabled": False,
            "token": None,
            "project_allowed_roots": (),
        }
    return {
        "enabled": security["external_api_enabled"],
        "token": security["external_api_token"],
        "project_allowed_roots": tuple(security["external_api_project_allowed_roots"]),
    }


def _public_program_configuration_response(result: dict) -> dict:
    """Remove external API secrets from generic program-configuration responses."""
    public_result = deepcopy(result)
    for key in ("values", "current_values", "proposed_values"):
        values = public_result.get(key)
        if not isinstance(values, dict):
            continue
        security = values.get("security")
        if not isinstance(security, dict):
            continue
        external_api_token = security.pop("external_api_token", None)
        security["external_api_token_configured"] = bool(external_api_token)
    return public_result


def migrate_configuration_storage(preferences_path: str | Path) -> dict:
    path = Path(preferences_path)
    registry = build_builtin_configuration_registry()
    program_repository = FileProgramConfigurationRepository(path)
    legacy_preferences = program_repository.read_legacy_payload()
    program_result = migrate_program_configuration(
        repository=program_repository,
        registry=registry,
    )
    graph_repository = FileGraphConfigurationRepository(
        path.with_name("graph-preferences.json")
    )
    graph_result = migrate_graph_configuration(
        repository=graph_repository,
        registry=registry,
        legacy_preferences=legacy_preferences,
    )
    return {"program": program_result, "graph": graph_result}


# ===== Language packs (external, filesystem-loaded) =====
#
# UI text uses a Chinese-source-as-fallback model: zh-CN is the hardcoded
# literal in the components and is NEVER a language pack. Other languages are
# authored externally (by anyone) as a folder under the program directory's
# `languages/` subdir and loaded at runtime. This keeps official maintenance to
# zero and lets third parties add languages by dropping in a folder.
#
# Pack layout (per locale):
#   languages/<locale>/manifest.json   {locale, display_name, author?, version?}
#   languages/<locale>/**/*.json        namespaced message trees (any depth)
#
# Every *.json (except manifest.json) is deep-merged into one message tree. The
# folder structure is purely for maintainability (per-module files); it does not
# affect key namespaces — keys are whatever the JSON contents declare.

LANGUAGES_DIRECTORY_NAME = "languages"


def _languages_directory(preferences_path: Path) -> Path:
    return Path(preferences_path).parent / LANGUAGES_DIRECTORY_NAME


def _read_language_manifest(locale_dir: Path) -> dict | None:
    manifest_path = locale_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    locale = payload.get("locale")
    if not isinstance(locale, str) or not locale.strip():
        # Fall back to the directory name as the locale identifier.
        locale = locale_dir.name
    display_name = payload.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = locale
    manifest = {"locale": locale, "display_name": display_name}
    for optional_key in ("author", "version", "description"):
        value = payload.get(optional_key)
        if isinstance(value, str) and value.strip():
            manifest[optional_key] = value
    return manifest


def list_available_languages(preferences_path: Path) -> list[dict]:
    """Scan the languages directory and return manifests for valid packs."""
    directory = _languages_directory(preferences_path)
    if not directory.is_dir():
        return []
    manifests: list[dict] = []
    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        manifest = _read_language_manifest(entry)
        if manifest is not None:
            manifests.append(manifest)
    return manifests


def _deep_merge_into(target: dict, source: dict) -> None:
    for key, value in source.items():
        if (
            isinstance(value, dict)
            and isinstance(target.get(key), dict)
        ):
            _deep_merge_into(target[key], value)
        else:
            target[key] = value


def _namespace_for_pack_file(locale_dir: Path, json_path: Path) -> list[str]:
    """Derive the message-tree namespace from a pack file's relative path.

    ``framework.json``               -> ``["framework"]``
    ``nodegraph/execution.json``     -> ``["nodegraph", "execution"]``
    ``framework.commandBar.json``    -> ``["framework", "commandBar"]``
    ``preferences.json``             -> ``["preferences"]``

    Directory separators AND dots in the filename both introduce namespace
    levels, so a large namespace can be split across sibling files
    (``framework.commandBar.json`` + ``framework.statusBar.json``) or nested
    folders interchangeably. Translators author flat/nested keys inside each
    module file without repeating the module prefix; the loader nests the
    content under the path-derived namespace so it matches the frontend
    ``t()`` keys.
    """
    relative = json_path.relative_to(locale_dir)
    segments: list[str] = list(relative.parts[:-1])
    # The filename (minus the trailing ``.json``) contributes one segment per
    # dot-delimited part, e.g. ``framework.commandBar`` -> framework, commandBar.
    filename = relative.parts[-1]
    if filename.endswith(".json"):
        filename = filename[: -len(".json")]
    segments.extend(part for part in filename.split(".") if part)
    return segments


def load_language_pack(preferences_path: Path, locale: str) -> dict | None:
    """Merge every JSON (except manifest) under languages/<locale>/.

    Each file's content is nested under the namespace derived from its path
    (see :func:`_namespace_for_pack_file`), then deep-merged into the tree.
    Returns the merged message tree, or None if the locale pack is absent.
    """
    directory = _languages_directory(preferences_path)
    # Resolve the locale to an actual pack directory (match manifest locale or
    # directory name); iterating manifests avoids trusting the locale string as
    # a filesystem path, so a traversal payload never reaches ``/`` operations.
    if not directory.is_dir():
        return None
    locale_dir: Path | None = None
    for entry in directory.iterdir():
        if not entry.is_dir():
            continue
        manifest = _read_language_manifest(entry)
        if manifest is not None and manifest["locale"] == locale:
            locale_dir = entry
            break
    if locale_dir is None:
        return None
    merged: dict = {}
    for json_path in sorted(locale_dir.rglob("*.json")):
        if json_path.name == "manifest.json":
            continue
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        namespace = _namespace_for_pack_file(locale_dir, json_path)
        scoped: dict = {}
        cursor = scoped
        for segment in namespace:
            child: dict = {}
            cursor[segment] = child
            cursor = child
        cursor.update(payload)
        _deep_merge_into(merged, scoped)
    return merged


# ===== Startup diagnostics & recovery =====
#
# On startup the desktop shell must be able to report *why* it failed even when
# the full workbench service cannot be constructed (e.g. a preferences or
# workspace-state file left behind by a different program version). These
# helpers probe each persisted file independently and never raise, so the
# diagnostics endpoint stays available while the rest of the API is dead.

# Severity tiers surfaced to the UI:
#   "critical" — 无法启动: unrecoverable, the app cannot run.
#   "fault"    — 故障: corrupt/incompatible config blocks startup, but the app
#                 can be force-started after backing up + resetting the file.
#   "anomaly"  — 异常: a startup problem that does not block usage.
#   "ok"       — subsystem is healthy.
_STARTUP_SEVERITY_RANK = {"ok": 0, "anomaly": 1, "fault": 2, "critical": 3}


def _worst_startup_severity(severities: list[str]) -> str:
    worst = "ok"
    for severity in severities:
        if _STARTUP_SEVERITY_RANK.get(severity, 0) > _STARTUP_SEVERITY_RANK[worst]:
            worst = severity
    return worst


def _diagnose_workspace_state(path: Path) -> dict:
    """workspace-state.json is required to build the service; corruption blocks startup."""
    subsystem = {
        "subsystem": "workspace_state",
        "label": "工作区状态",
        "location": str(path),
        "status": "ok",
        "severity": "ok",
        "error_code": None,
        "message": "工作区状态正常",
        "recoverable": False,
        "recovery_target": "workspace_state",
    }
    if not path.exists():
        subsystem["message"] = "工作区状态文件不存在，将在启动时自动创建"
        return subsystem
    try:
        FileWorkspaceStateStore(path).load()
    except ValueError as exc:
        subsystem.update(
            status="invalid",
            severity="fault",
            error_code="workspace_state_invalid",
            message=str(exc),
            recoverable=True,
        )
    except OSError as exc:
        subsystem.update(
            status="unreadable",
            severity="critical",
            error_code="workspace_state_unreadable",
            message=f"无法读取工作区状态文件: {exc}",
            recoverable=False,
        )
    return subsystem


def _diagnose_program_configuration(path: Path) -> dict:
    """preferences.json — tolerated by the loader (falls back to defaults) → anomaly."""
    subsystem = {
        "subsystem": "preferences",
        "label": "首选项配置",
        "location": str(path),
        "status": "ok",
        "severity": "ok",
        "error_code": None,
        "message": "首选项配置正常",
        "recoverable": False,
        "recovery_target": "preferences",
    }
    if not path.exists():
        subsystem["message"] = "首选项文件不存在，将使用默认配置"
        return subsystem
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        subsystem.update(
            status="unreadable",
            severity="critical",
            error_code="preferences_unreadable",
            message=f"无法读取首选项文件: {exc}",
            recoverable=False,
        )
        return subsystem
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        subsystem.update(
            status="invalid_json",
            severity="anomaly",
            error_code="preferences_invalid_json",
            message=f"首选项文件不是合法 JSON（将回退默认配置）: {exc}",
            recoverable=True,
        )
        return subsystem
    if not FileProgramConfigurationRepository.is_current_payload(payload):
        subsystem.update(
            status="incompatible",
            severity="anomaly",
            error_code="preferences_incompatible_format",
            message="首选项文件为旧版本或不兼容格式，将迁移/回退默认配置",
            recoverable=True,
        )
    return subsystem


def _diagnose_graph_configuration(path: Path) -> dict:
    """graph-preferences.json — tolerated by the loader → anomaly."""
    subsystem = {
        "subsystem": "graph_preferences",
        "label": "图编辑器配置",
        "location": str(path),
        "status": "ok",
        "severity": "ok",
        "error_code": None,
        "message": "图编辑器配置正常",
        "recoverable": False,
        "recovery_target": "graph_preferences",
    }
    if not path.exists():
        subsystem["message"] = "图配置文件不存在，将使用默认配置"
        return subsystem
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        subsystem.update(
            status="unreadable",
            severity="anomaly",
            error_code="graph_preferences_unreadable",
            message=f"无法读取图配置文件（将回退默认配置）: {exc}",
            recoverable=True,
        )
        return subsystem
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        subsystem.update(
            status="invalid_json",
            severity="anomaly",
            error_code="graph_preferences_invalid_json",
            message=f"图配置文件不是合法 JSON（将回退默认配置）: {exc}",
            recoverable=True,
        )
        return subsystem
    if not FileGraphConfigurationRepository.is_current_payload(payload):
        subsystem.update(
            status="incompatible",
            severity="anomaly",
            error_code="graph_preferences_incompatible_format",
            message="图配置文件为旧版本或不兼容格式，将迁移/回退默认配置",
            recoverable=True,
        )
    return subsystem


def build_startup_diagnostics(
    preferences_path: str | Path,
    workspace_state_path: str | Path | None = None,
) -> dict:
    """Probe every persisted startup file and classify the overall severity."""
    preferences_path = Path(preferences_path)
    workspace_state_path = (
        Path(workspace_state_path)
        if workspace_state_path is not None
        else preferences_path.with_name("workspace-state.json")
    )
    graph_path = preferences_path.with_name("graph-preferences.json")

    subsystems = [
        _diagnose_workspace_state(workspace_state_path),
        _diagnose_program_configuration(preferences_path),
        _diagnose_graph_configuration(graph_path),
    ]
    overall_severity = _worst_startup_severity([s["severity"] for s in subsystems])
    recoverable_targets = [
        s["recovery_target"] for s in subsystems if s["recoverable"]
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_severity": overall_severity,
        "recoverable_targets": recoverable_targets,
        "subsystems": subsystems,
    }


def _backup_corrupt_file(path: Path) -> str | None:
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.corrupt-{timestamp}.bak")
    counter = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.corrupt-{timestamp}-{counter}.bak")
        counter += 1
    backup_path.write_bytes(path.read_bytes())
    return str(backup_path)


def recover_startup_target(
    target: str,
    preferences_path: str | Path,
    workspace_state_path: str | Path | None = None,
) -> dict:
    """Back up and reset a corrupt startup file so the app can start on defaults."""
    preferences_path = Path(preferences_path)
    registry = build_builtin_configuration_registry()

    if target == "workspace_state":
        path = (
            Path(workspace_state_path)
            if workspace_state_path is not None
            else preferences_path.with_name("workspace-state.json")
        )
        backup = _backup_corrupt_file(path)
        # Remove the corrupt file; the workbench service rebuilds a valid default
        # workspace state on next load.
        if path.exists():
            path.unlink()
        return {
            "target": target,
            "status": "reset",
            "location": str(path),
            "backup_path": backup,
            "message": "已备份并重置工作区状态，将在启动时重建默认状态",
        }

    if target == "preferences":
        path = preferences_path
        backup = _backup_corrupt_file(path)
        repository = FileProgramConfigurationRepository(path)
        ConfigurationService(
            registry=registry,
            repositories={"program": repository},
        ).reset(scope="program")
        return {
            "target": target,
            "status": "reset",
            "location": str(path),
            "backup_path": backup,
            "message": "已备份并重置首选项为默认配置",
        }

    if target == "graph_preferences":
        path = preferences_path.with_name("graph-preferences.json")
        backup = _backup_corrupt_file(path)
        repository = FileGraphConfigurationRepository(path)
        ConfigurationService(
            registry=registry,
            repositories={"graph": repository},
        ).reset(scope="graph")
        return {
            "target": target,
            "status": "reset",
            "location": str(path),
            "backup_path": backup,
            "message": "已备份并重置图编辑器配置为默认配置",
        }

    raise ValueError(f"unknown recovery target: {target}")


class ApiServerClosingError(ValueError):
    pass


def _sanitize_path_for_error(path: str) -> str:
    sanitized = "".join(char for char in path if char.isprintable() or char in " \t")
    if len(sanitized) > 200:
        sanitized = sanitized[:200] + "...(truncated)"
    return sanitized


def _is_path_under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


class WeConductApiServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

    def __init__(self, *args, **kwargs) -> None:
        self._service_lock = RLock()
        self._debug_action_condition = Condition(RLock())
        self._active_debug_action_count = 0
        self._closing = False
        self.external_api_enabled = False
        self.external_api_token: str | None = None
        self.external_api_project_allowed_roots: tuple[Path, ...] = ()
        self.external_api_instance_id = uuid.uuid4().hex
        self.external_api_audit_trail = InMemoryOperationAuditTrail()
        self.external_api_idempotency_store = InMemoryOperationIdempotencyStore(
            limit=EXTERNAL_IDEMPOTENCY_CACHE_LIMIT
        )
        super().__init__(*args, **kwargs)

    def execute_debug_action(
        self,
        action: Callable[[], DebugActionResult],
    ) -> DebugActionResult:
        with self._debug_action_condition:
            if self._closing:
                raise ApiServerClosingError("API server is closing")
            self._active_debug_action_count += 1
        try:
            return action()
        finally:
            with self._debug_action_condition:
                self._active_debug_action_count -= 1
                if self._active_debug_action_count == 0:
                    self._debug_action_condition.notify_all()

    def server_close(self) -> None:
        try:
            with self._debug_action_condition:
                self._closing = True
                while self._active_debug_action_count > 0:
                    self._debug_action_condition.wait()
            service = getattr(self, "workbench_service", None)
            if isinstance(service, CompilationWorkbenchService):
                service.shutdown_debug_sessions()
        finally:
            super().server_close()


class WeConductApiHandler(BaseHTTPRequestHandler):
    def _handle_external_api(self, *, method: str) -> bool:
        """将外部 v1 请求交给独立 adapter，内部 UI API 保持在本 handler。"""
        return ExternalV1Router(self).handle(method=method)

    def _verify_api_token(self) -> bool:
        expected_token = getattr(self.server, "api_token", None)
        if expected_token is None:
            return True
        provided_token = self.headers.get("X-WeConduct-Token", "")
        return secrets.compare_digest(provided_token, expected_token)

    def _require_api_token(self) -> bool:
        if self._verify_api_token():
            return True
        self._write_json(
            HTTPStatus.UNAUTHORIZED,
            {
                "error": "unauthorized",
                "message": "invalid or missing API token",
            },
        )
        return False

    def do_GET(self) -> None:  # noqa: N802
        if self._handle_external_api(method="GET"):
            return
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        request_path = parsed_url.path

        # Static UI assets (index.html, JS, CSS) must be served WITHOUT the
        # workbench service. Otherwise a corrupt workspace-state/preferences file
        # makes _get_service() throw for "/" too, the SPA never boots, and the
        # dedicated startup error screen can never render. This has no service or
        # token dependency and ignores /api/ paths, so it is safe up front.
        if not request_path.startswith("/api/"):
            if self._try_serve_ui_asset():
                return

        # Startup diagnostics must stay reachable even when the workbench service
        # cannot be constructed, so it runs before _get_service().
        if request_path == "/api/startup/diagnostics":
            self._handle_startup_diagnostics()
            return

        try:
            service = self._get_service()
        except ValueError as exc:
            # /api/health is a liveness probe: report a degraded (but reachable)
            # status with structured startup diagnostics instead of a bare error,
            # so the UI can render the dedicated startup error screen.
            if request_path == "/api/health":
                self._write_degraded_health(exc)
                return
            self._write_workspace_state_error(exc)
            return
        if self.path == "/api/health":
            payload = dict(service.get_runtime_health())
            payload["ui_hosting"] = self._build_ui_hosting_metadata()
            self._write_json(HTTPStatus.OK, payload)
            return

        if not self._require_api_token():
            return

        if request_path == "/api/workbench/config/schema":
            try:
                scope = self._get_optional_query_param(query_params, "scope")
                if not isinstance(scope, str) or not scope.strip():
                    raise ValueError("query parameter must be a non-empty string: scope")
                result = self._get_configuration_service().get_schema(scope=scope)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if request_path == "/api/workbench/config/values":
            try:
                scope = self._get_optional_query_param(query_params, "scope")
                if not isinstance(scope, str) or not scope.strip():
                    raise ValueError("query parameter must be a non-empty string: scope")
                result = self._get_configuration_service().get_values(scope=scope)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                _public_program_configuration_response(result)
                if scope == "program"
                else result,
            )
            return

        if request_path == "/api/workbench/preferences/external-api":
            self._write_json(HTTPStatus.OK, self._get_external_api_preferences_summary())
            return

        if self.path == "/api/workbench/snapshot":
            payload = dict(service.get_workbench_snapshot())
            payload["ui_hosting"] = self._build_ui_hosting_metadata()
            self._write_json(HTTPStatus.OK, payload)
            return

        if request_path == "/api/workbench/graph":
            try:
                result = service.get_graph_document(
                    document_id=self._get_optional_query_param(query_params, "document_id")
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "graph_model": result["graph_model"].model_dump(),
                    "view": result["view"],
                },
            )
            return

        if request_path == "/api/workbench/graph/node-draft":
            try:
                resource_key = self._get_optional_query_param(query_params, "resource_key")
                if not isinstance(resource_key, str) or not resource_key.strip():
                    raise ValueError("query parameter must be a non-empty string: resource_key")
                raw_node_id = self._get_optional_query_param(query_params, "node_id")
                x_value = self._get_optional_float_query_param(query_params, "x")
                y_value = self._get_optional_float_query_param(query_params, "y")
                position = None
                if x_value is not None and y_value is not None:
                    position = {"x": x_value, "y": y_value}
                result = service.build_graph_node_draft(
                    resource_key=resource_key,
                    node_id=raw_node_id,
                    position=position,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/graph/source-projection":
            try:
                result = service.get_graph_source_projection_document(
                    target_source_kind="native_flow",
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "ready" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/project":
            result = service.get_project_document()
            project_settings = deepcopy(result.get("project_settings"))
            if isinstance(project_settings, dict):
                project_settings.pop("encrypted_parameter_set", None)
            self._write_json(
                HTTPStatus.OK,
                {
                    "project": result["project"],
                    "project_settings": project_settings,
                    "encrypted_parameter_summary": service.get_project_encrypted_parameter_summary(),
                    "graph_workspace": result["graph_workspace"],
                },
            )
            return

        if self.path == "/api/workbench/project/encrypted-parameters":
            self._write_json(HTTPStatus.OK, service.get_project_encrypted_parameter_summary())
            return

        if self.path == "/api/workbench/project/python-runtime":
            result = service.get_project_python_runtime_document()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if self.path == "/api/workbench/project/package/preflight":
            result = service.run_project_package_preflight()
            status_code = HTTPStatus.OK if result["status"] == "ok" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if request_path == "/api/workbench/project/package/inspect":
            try:
                package_path = self._get_optional_query_param(query_params, "package_path")
                if not isinstance(package_path, str) or not package_path.strip():
                    raise ValueError("query parameter must be a non-empty string: package_path")
                result = service.inspect_project_package(package_path=package_path)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/update/status":
            result = self._get_update_service().get_status()
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/recent-projects":
            result = service.get_recent_projects_document()
            self._write_json(
                HTTPStatus.OK,
                {
                    "recent_projects": result["recent_projects"],
                },
            )
            return

        if request_path == "/api/workbench/languages":
            prefs_path = self._resolve_preferences_path()
            manifests = list_available_languages(prefs_path)
            languages_dir = _languages_directory(prefs_path)
            # Ensure the directory exists so the "open data dir" button always
            # has a real target (packs are user-authored; the dir may be absent
            # on a fresh install).
            try:
                languages_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            self._write_json(
                HTTPStatus.OK,
                {
                    "languages": manifests,
                    "languages_directory": str(languages_dir),
                },
            )
            return

        if request_path.startswith("/api/workbench/languages/"):
            locale = unquote(request_path[len("/api/workbench/languages/"):]).strip()
            if not locale:
                self._write_invalid_request_error(
                    ValueError("path parameter must be a non-empty string: locale")
                )
                return
            messages = load_language_pack(self._resolve_preferences_path(), locale)
            if messages is None:
                self._write_json(
                    HTTPStatus.NOT_FOUND,
                    {
                        "error": "language.pack_not_found",
                        "message": f"no language pack found for locale: {locale}",
                    },
                )
                return
            self._write_json(
                HTTPStatus.OK,
                {"locale": locale, "messages": messages},
            )
            return

        if request_path == "/api/workbench/resources":
            result = service.get_resource_registry_document(
                query=self._get_optional_query_param(query_params, "query"),
                tags=self._get_multi_query_param(query_params, "tags"),
                enabled=self._get_optional_bool_query_param(query_params, "enabled"),
                origin=self._get_optional_query_param(query_params, "origin"),
                resource_type=self._get_optional_query_param(query_params, "resource_type"),
            )
            self._write_json(
                HTTPStatus.OK,
                {
                    "registry_revision": result["registry_revision"],
                    "resource_types": result["resource_types"],
                    "summary": result["summary"],
                    "facets": result["facets"],
                    "resources": result["resources"],
                },
            )
            return

        if self.path == "/api/workbench/project/documents":
            result = service.get_project_documents_document()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if self.path == "/api/workbench/project/resource-audit":
            result = service.get_project_resource_audit_document()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if request_path == "/api/workbench/component-library":
            result = service.get_component_library_document(
                query=self._get_optional_query_param(query_params, "query"),
                tags=self._get_multi_query_param(query_params, "tags"),
                enabled=self._get_optional_bool_query_param(query_params, "enabled"),
                origin=self._get_optional_query_param(query_params, "origin"),
                resource_type=self._get_optional_query_param(query_params, "resource_type"),
            )
            self._write_json(
                HTTPStatus.OK,
                {
                    "summary": result["summary"],
                    "facets": result["facets"],
                    "items": result["items"],
                },
            )
            return

        if self.path == "/api/workbench/editor/history":
            result = service.get_editor_history_document()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if request_path == "/api/workbench/execution-history":
            result = service.get_execution_history_document(
                runtime_status=self._get_optional_query_param(query_params, "runtime_status"),
                debug_status=self._get_optional_query_param(query_params, "debug_status"),
            )
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if self.path == "/api/workbench/runtime/sessions":
            result = service.list_runtime_sessions()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if self.path == "/api/workbench/debug/sessions":
            result = service.list_debug_sessions()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if request_path == "/api/workbench/debug/history":
            result = service.list_debug_history_sessions()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if request_path.startswith("/api/workbench/debug/history/"):
            session_id = request_path.removeprefix("/api/workbench/debug/history/")
            if session_id and "/" not in session_id:
                try:
                    result = service.open_debug_history_session(session_id=session_id)
                except ValueError as exc:
                    self._write_invalid_request_error(exc)
                    return
                self._write_json(HTTPStatus.OK, result)
                return

        if request_path.startswith("/api/workbench/debug/") and request_path.endswith("/events"):
            session_id = request_path.removeprefix("/api/workbench/debug/").removesuffix("/events")
            if session_id and "/" not in session_id:
                try:
                    result = service.list_debug_session_events(session_id=session_id)
                except ValueError as exc:
                    self._write_invalid_request_error(exc)
                    return
                self._write_json(HTTPStatus.OK, result)
                return

        if request_path.startswith("/api/workbench/debug/projection/live/"):
            session_id = request_path.removeprefix("/api/workbench/debug/projection/live/")
            if session_id and "/" not in session_id:
                try:
                    result = service.get_debug_live_projection(session_id=session_id)
                except ValueError as exc:
                    self._write_invalid_request_error(exc)
                    return
                self._write_json(HTTPStatus.OK, result)
                return

        if request_path.startswith("/api/workbench/debug/projection/history/"):
            session_id = request_path.removeprefix("/api/workbench/debug/projection/history/")
            if session_id and "/" not in session_id:
                try:
                    event_index = None
                    keyframe_id = None
                    raw_event_indexes = query_params.get("event_index")
                    if raw_event_indexes:
                        event_index = int(raw_event_indexes[0])
                        if event_index < 0:
                            raise ValueError("event_index must be a non-negative integer")
                    raw_keyframe_ids = query_params.get("keyframe_id")
                    if raw_keyframe_ids:
                        keyframe_id = raw_keyframe_ids[0].strip()
                        if not keyframe_id:
                            raise ValueError("keyframe_id must be a non-empty string")
                    result = service.get_debug_history_projection(
                        session_id=session_id,
                        event_index=event_index,
                        keyframe_id=keyframe_id,
                    )
                except (TypeError, ValueError) as exc:
                    self._write_invalid_request_error(exc)
                    return
                self._write_json(HTTPStatus.OK, result)
                return

        if self.path.startswith("/api/workbench/runtime/") and self.command == "GET":
            session_id = self.path.removeprefix("/api/workbench/runtime/")
            if session_id.endswith("/stream"):
                runtime_session_id = session_id.removesuffix("/stream")
                if runtime_session_id and "/" not in runtime_session_id:
                    try:
                        self._write_runtime_stream(service, runtime_session_id)
                    except ValueError as exc:
                        self._write_invalid_request_error(exc)
                    return
            if session_id.endswith("/pending-input"):
                runtime_session_id = session_id.removesuffix("/pending-input")
                if runtime_session_id and "/" not in runtime_session_id:
                    try:
                        snapshot = service.get_pending_input_snapshot(
                            execution_id=runtime_session_id
                        )
                    except ValueError as exc:
                        self._write_invalid_request_error(exc)
                        return
                    self._write_json(HTTPStatus.OK, _public_pending_input_snapshot(snapshot))
                    return
            if session_id and "/" not in session_id:
                try:
                    result = service.get_runtime_session(session_id=session_id)
                except ValueError as exc:
                    self._write_invalid_request_error(exc)
                    return
                self._write_json(HTTPStatus.OK, result)
                return

        if self.path.startswith("/api/workbench/debug/") and self.command == "GET":
            session_id = self.path.removeprefix("/api/workbench/debug/")
            if session_id and "/" not in session_id:
                try:
                    result = service.get_debug_session(session_id=session_id)
                except ValueError as exc:
                    self._write_invalid_request_error(exc)
                    return
                self._write_json(HTTPStatus.OK, result)
                return

        if self.path == "/api/host/info":
            service_health = service.get_runtime_health()
            payload = {
                "host_mode": service_health["host_mode"],
                "api_version": service_health["api_version"],
                "server_bind": self._build_server_bind_metadata(),
                "ui_hosting": self._build_ui_hosting_metadata(),
                "release_manifest": self._build_release_manifest(),
            }
            self._write_json(HTTPStatus.OK, payload)
            return

        if self._try_serve_ui_asset():
            return

        self._write_not_found_error()

    def do_PATCH(self) -> None:  # noqa: N802
        if not self._require_api_token():
            return
        if urlparse(self.path).path != "/api/workbench/config/values":
            self._write_not_found_error()
            return
        try:
            payload = self._read_json_request_body()
            scope = payload.get("scope")
            operations = payload.get("operations")
            confirm_high_risk = payload.get("confirm_high_risk", False)
            if not isinstance(scope, str) or not scope.strip():
                raise ValueError("field must be a non-empty string: scope")
            if not isinstance(operations, list):
                raise ValueError("field must be a JSON array: operations")
            if not isinstance(confirm_high_risk, bool):
                raise ValueError("field must be a boolean: confirm_high_risk")
            result = self._get_configuration_service().apply(
                scope=scope,
                operations=operations,
                confirm_high_risk=confirm_high_risk,
            )
        except HighRiskConfigurationChangeRequiredError as exc:
            self._write_high_risk_configuration_confirmation_required_error(exc)
            return
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return
        self._write_json(
            HTTPStatus.OK,
            _public_program_configuration_response(result)
            if scope == "program"
            else result,
        )

    def do_POST(self) -> None:  # noqa: N802
        if self._handle_external_api(method="POST"):
            return
        if self.path == "/api/host/file-dialog":
            if not self._require_api_token():
                return
            self._handle_host_file_dialog()
            return

        if self.path == "/api/host/open-path":
            if not self._require_api_token():
                return
            self._handle_host_open_path()
            return

        if self.path == "/api/host/read-file":
            if not self._require_api_token():
                return
            self._handle_host_read_file()
            return

        # Startup recovery must stay reachable even when the workbench service
        # cannot be constructed, so it runs before _get_service().
        if self.path == "/api/startup/recover":
            self._handle_startup_recover()
            return

        try:
            service = self._get_service()
        except ValueError as exc:
            self._write_workspace_state_error(exc)
            return
        if self.path == "/api/workbench/compile":
            try:
                payload = self._read_json_request_body()
                self._validate_compile_payload(payload)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            result = service.compile_source(
                source_kind=payload["source_kind"],
                entry_document=payload["entry_document"],
                source_text=payload["source_text"],
            )
            response_payload = {
                "status": result["status"],
                "request": self._serialize_request(result["request"]),
                "outcome": result["outcome"].model_dump(),
                "view": result["view"],
            }
            if result["status"] == "failed":
                response_payload.update(
                    self._build_compile_failure_error_payload(
                        result,
                        error_code="compile_failed",
                    )
                )
            response_status = (
                HTTPStatus.BAD_REQUEST
                if result["status"] == "failed"
                else HTTPStatus.OK
            )
            self._write_json(response_status, response_payload)
            return

        if self.path == "/api/workbench/graph/validate":
            try:
                payload = self._read_json_request_body()
                result = service.validate_graph_document(payload)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "summary": result["summary"],
                    "diagnostics": result["diagnostics"],
                },
            )
            return

        if self.path == "/api/workbench/graph/compile":
            try:
                payload = self._read_optional_json_request_body()
                result = service.compile_graph_document(payload)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "request": self._serialize_request(result["request"]),
                    "outcome": result["outcome"].model_dump(),
                    "view": result["view"],
                },
            )
            return

        if self.path == "/api/workbench/graph/normalize":
            try:
                payload = self._read_json_request_body()
                result = service.normalize_graph_document(payload)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "changed": result["changed"],
                    "graph_model": result["graph_model"].model_dump(),
                    "view": result["view"],
                },
            )
            return

        if self.path == "/api/workbench/runtime/prepare":
            try:
                payload = self._read_optional_json_request_body()
                result = service.prepare_runtime_session(
                    self._extract_optional_graph_document_payload(payload)
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "ready" else HTTPStatus.BAD_REQUEST
            response_payload = dict(result)
            if result["status"] != "ready":
                response_payload.update(
                    self._build_runtime_failure_error_payload(
                        result,
                        error_code="runtime_prepare_failed",
                    )
                )
            self._write_json(status_code, response_payload)
            return

        if self.path == "/api/workbench/runtime/start":
            try:
                payload = self._read_optional_json_request_body()
                result = service.start_runtime_session(
                    self._extract_optional_graph_document_payload(payload)
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "started" else HTTPStatus.BAD_REQUEST
            response_payload = dict(result)
            if result["status"] != "started":
                response_payload.update(
                    self._build_runtime_failure_error_payload(
                        result,
                        error_code="runtime_start_failed",
                    )
                )
            self._write_json(status_code, response_payload)
            return

        if self.path.startswith("/api/workbench/runtime/") and self.path.endswith("/run"):
            try:
                session_id = self.path.removeprefix("/api/workbench/runtime/").removesuffix("/run")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid runtime session path")
                self._read_optional_json_request_body()
                result = service.start_runtime_session_execution(session_id=session_id)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK
                if result["status"] in {"accepted", "completed", "failed", "unlock_required"}
                else HTTPStatus.BAD_REQUEST
            )
            response_payload = dict(result)
            if result["status"] == "failed":
                response_payload.update(
                    self._build_runtime_failure_error_payload(
                        result,
                        error_code="runtime_run_failed",
                    )
                )
            self._write_json(status_code, response_payload)
            return
        if self.path.startswith("/api/workbench/runtime/") and self.path.endswith("/pending-input"):
            try:
                session_id = self.path.removeprefix("/api/workbench/runtime/").removesuffix("/pending-input")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid runtime session path")
                payload = self._read_json_request_body()
                request_id = payload.get("request_id")
                values = payload.get("values")
                if not isinstance(request_id, str) or not request_id.strip():
                    raise ValueError("field must be a non-empty string: request_id")
                if not isinstance(values, dict):
                    raise ValueError("field must be an object: values")
                snapshot = service.submit_pending_input(
                    execution_id=session_id,
                    request_id=request_id,
                    values=values,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, _public_pending_input_snapshot(snapshot))
            return
        if self.path.startswith("/api/workbench/runtime/") and self.path.endswith("/unlock"):
            try:
                session_id = self.path.removeprefix("/api/workbench/runtime/").removesuffix("/unlock")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid runtime session path")
                payload = self._read_json_request_body()
                password = payload.get("password")
                if not isinstance(password, str) or not password:
                    raise ValueError("field must be a non-empty string: password")
                result = service.unlock_runtime_session_parameters(
                    session_id=session_id,
                    password=password,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return
        if self.path == "/api/workbench/config/preview":
            try:
                payload = self._read_json_request_body()
                scope = payload.get("scope")
                operations = payload.get("operations")
                if not isinstance(scope, str) or not scope.strip():
                    raise ValueError("field must be a non-empty string: scope")
                result = self._get_configuration_service().preview(
                    scope=scope,
                    operations=operations,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                _public_program_configuration_response(result)
                if scope == "program"
                else result,
            )
            return

        if self.path == "/api/workbench/config/reset":
            try:
                payload = self._read_json_request_body()
                scope = payload.get("scope")
                if not isinstance(scope, str) or not scope.strip():
                    raise ValueError("field must be a non-empty string: scope")
                result = self._get_configuration_service().reset(scope=scope)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                _public_program_configuration_response(result)
                if scope == "program"
                else result,
            )
            return

        if self.path == "/api/workbench/preferences/external-api":
            try:
                payload = self._read_json_request_body()
                result = self._update_external_api_preferences(payload)
            except HighRiskConfigurationChangeRequiredError as exc:
                self._write_high_risk_configuration_confirmation_required_error(exc)
                return
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path.startswith("/api/workbench/runtime/") and self.path.endswith("/abort"):
            try:
                session_id = self.path.removeprefix("/api/workbench/runtime/").removesuffix("/abort")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid runtime session path")
                payload = self._read_json_request_body()
                reason = payload.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError("field must be a non-empty string: reason")
                result = service.abort_runtime_session(
                    session_id=session_id,
                    reason=reason,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK
                if result["status"] in {
                    "aborting",
                    "aborted",
                    "completed",
                    "failed",
                }
                else HTTPStatus.BAD_REQUEST
            )
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/debug/prepare":
            try:
                payload = self._read_optional_json_request_body()
                result = service.prepare_debug_session(
                    self._extract_optional_graph_document_payload(payload)
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "ready" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/debug/start":
            try:
                payload = self._read_optional_json_request_body()
                result = self.server.execute_debug_action(
                    lambda: service.start_debug_session_async(
                        self._extract_optional_graph_document_payload(payload)
                    )
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK
                if result["status"] in {"started", "running", "paused", "completed", "failed", "aborted", "incomplete"}
                else HTTPStatus.BAD_REQUEST
            )
            self._write_json(status_code, result)
            return

        if self.path.startswith("/api/workbench/debug/") and self.path.endswith("/continue"):
            try:
                session_id = self.path.removeprefix("/api/workbench/debug/").removesuffix("/continue")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid debug session path")
                self._read_optional_json_request_body()
                result = self.server.execute_debug_action(
                    lambda: service.continue_debug_session_async(
                        session_id=session_id,
                        settle_timeout_ms=500,
                    )
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK
                if result["status"] in {"accepted", "running", "paused", "completed", "failed", "aborted", "incomplete"}
                else HTTPStatus.BAD_REQUEST
            )
            self._write_json(status_code, result)
            return

        if self.path.startswith("/api/workbench/debug/") and self.path.endswith("/pause"):
            try:
                session_id = self.path.removeprefix("/api/workbench/debug/").removesuffix("/pause")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid debug session path")
                payload = self._read_json_request_body()
                node_id = payload.get("node_id")
                reason = payload.get("reason")
                if node_id is not None and (not isinstance(node_id, str) or not node_id.strip()):
                    raise ValueError("field must be a non-empty string when provided: node_id")
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError("field must be a non-empty string: reason")
                result = self.server.execute_debug_action(
                    lambda: service.request_debug_pause(
                        session_id=session_id,
                        node_id=node_id,
                        reason=reason,
                    )
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK
                if result["status"] in {"accepted", "paused", "completed", "failed", "aborted", "incomplete"}
                else HTTPStatus.BAD_REQUEST
            )
            self._write_json(status_code, result)
            return

        if self.path.startswith("/api/workbench/debug/") and self.path.endswith("/variables/apply"):
            try:
                session_id = (
                    self.path.removeprefix("/api/workbench/debug/").removesuffix("/variables/apply")
                )
                if not session_id or "/" in session_id:
                    raise ValueError("invalid debug session path")
                payload = self._read_json_request_body()
                updates = payload.get("updates")
                apply_mode = payload.get("apply_mode", "staged")
                if not isinstance(updates, dict):
                    raise ValueError("field must be a JSON object: updates")
                if not isinstance(apply_mode, str):
                    raise ValueError("field must be a string when provided: apply_mode")
                result = self.server.execute_debug_action(
                    lambda: service.apply_debug_session_variables(
                        session_id=session_id,
                        updates=updates,
                        apply_mode=apply_mode,
                    )
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "updated" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path.startswith("/api/workbench/debug/") and self.path.endswith("/debugger-config/apply"):
            try:
                session_id = (
                    self.path.removeprefix("/api/workbench/debug/")
                    .removesuffix("/debugger-config/apply")
                )
                if not session_id or "/" in session_id:
                    raise ValueError("invalid debug session path")
                payload = self._read_json_request_body()
                node_id = payload.get("node_id")
                debugger_config = payload.get("debugger")
                if not isinstance(node_id, str) or not node_id.strip():
                    raise ValueError("field must be a non-empty string: node_id")
                if not isinstance(debugger_config, dict):
                    raise ValueError("field must be a JSON object: debugger")
                result = self.server.execute_debug_action(
                    lambda: service.update_debug_session_node_debugger(
                        session_id=session_id,
                        node_id=node_id,
                        debugger_config=debugger_config,
                    )
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "updated" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path.startswith("/api/workbench/debug/") and self.path.endswith("/step-over"):
            try:
                session_id = self.path.removeprefix("/api/workbench/debug/").removesuffix("/step-over")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid debug session path")
                self._read_optional_json_request_body()
                result = self.server.execute_debug_action(
                    lambda: service.step_over_debug_session_async(session_id=session_id)
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK
                if result["status"] in {"accepted", "stepping", "paused", "completed", "failed", "aborted", "incomplete"}
                else HTTPStatus.BAD_REQUEST
            )
            self._write_json(status_code, result)
            return

        if self.path.startswith("/api/workbench/debug/") and self.path.endswith("/step-into"):
            try:
                session_id = self.path.removeprefix("/api/workbench/debug/").removesuffix("/step-into")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid debug session path")
                self._read_optional_json_request_body()
                result = self.server.execute_debug_action(
                    lambda: service.step_into_debug_session_async(session_id=session_id)
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK
                if result["status"] in {"accepted", "stepping", "paused", "completed", "failed", "aborted", "incomplete"}
                else HTTPStatus.BAD_REQUEST
            )
            self._write_json(status_code, result)
            return

        if self.path.startswith("/api/workbench/debug/") and self.path.endswith("/step-out"):
            try:
                session_id = self.path.removeprefix("/api/workbench/debug/").removesuffix("/step-out")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid debug session path")
                self._read_optional_json_request_body()
                result = self.server.execute_debug_action(
                    lambda: service.step_out_debug_session_async(session_id=session_id)
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK
                if result["status"] in {"accepted", "stepping", "paused", "completed", "failed", "aborted", "incomplete"}
                else HTTPStatus.BAD_REQUEST
            )
            self._write_json(status_code, result)
            return

        if self.path.startswith("/api/workbench/debug/") and self.path.endswith("/abort"):
            try:
                session_id = self.path.removeprefix("/api/workbench/debug/").removesuffix("/abort")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid debug session path")
                payload = self._read_json_request_body()
                reason = payload.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError("field must be a non-empty string: reason")
                result = self.server.execute_debug_action(
                    lambda: service.abort_debug_session(
                        session_id=session_id,
                        reason=reason,
                    )
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK
                if result["status"] in {"accepted", "aborted", "completed", "failed", "incomplete"}
                else HTTPStatus.BAD_REQUEST
            )
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/project/new":
            try:
                payload = self._read_json_request_body()
                project_name = payload.get("project_name")
                if not isinstance(project_name, str):
                    raise ValueError("field must be a string: project_name")
                project_directory = payload.get("project_directory")
                if project_directory is not None and not isinstance(project_directory, str):
                    raise ValueError("field must be a string: project_directory")
                result = service.create_project(
                    project_name=project_name,
                    project_directory=project_directory,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "project": result["project"],
                    "graph_document": result["graph_document"].model_dump(),
                },
            )
            return

        if self.path == "/api/workbench/project/encrypted-parameters":
            try:
                payload = self._read_json_request_body()
                result = service.configure_project_encrypted_parameters(
                    parameter_set_id=payload.get("parameter_set_id"),
                    parameters=payload.get("parameters"),
                    values=payload.get("values"),
                    password=payload.get("password"),
                    confirm_overwrite=payload.get("confirm_overwrite", False),
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/encrypted-parameters/rekey":
            try:
                payload = self._read_json_request_body()
                result = service.rekey_project_encrypted_parameters(
                    current_password=payload.get("current_password"),
                    new_password=payload.get("new_password"),
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/encrypted-parameters/delete":
            try:
                payload = self._read_json_request_body()
                result = service.clear_project_encrypted_parameters(
                    confirm_delete=payload.get("confirm_delete", False),
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/python-runtime/health-check":
            try:
                self._read_optional_json_request_body()
                result = service.health_check_project_python_runtime()
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/python-runtime/prepare":
            try:
                self._read_optional_json_request_body()
                result = service.prepare_project_python_runtime()
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/python-runtime/rebuild":
            try:
                self._read_optional_json_request_body()
                result = service.rebuild_project_python_runtime()
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/python-runtime/clear":
            try:
                self._read_optional_json_request_body()
                result = service.clear_project_python_runtime()
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/python-runtime/export-bundle":
            try:
                payload = self._read_json_request_body()
                output_path = payload.get("output_path")
                package_embed_mode = payload.get("package_embed_mode")
                if not isinstance(output_path, str) or not output_path.strip():
                    raise ValueError("field must be a non-empty string: output_path")
                if package_embed_mode is not None and not isinstance(package_embed_mode, str):
                    raise ValueError("field must be a string when provided: package_embed_mode")
                result = service.export_project_python_runtime_bundle(
                    output_path=output_path,
                    package_embed_mode=package_embed_mode,
                )
            except ProjectPythonRuntimeExportError as exc:
                self._write_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "error": "project_python_runtime_export_failed",
                        "message": str(exc),
                        "diagnostics": {
                            "total_count": len(exc.diagnostics),
                            "highest_severity": (
                                max(
                                    (
                                        entry.get("severity")
                                        for entry in exc.diagnostics
                                        if entry.get("severity") in DIAGNOSTIC_SEVERITIES
                                    ),
                                    key=lambda severity: DIAGNOSTIC_SEVERITY_RANK[severity],
                                    default=None,
                                )
                            ),
                            "entries": deepcopy(exc.diagnostics),
                        },
                    },
                )
                return
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/package/preflight":
            try:
                self._read_json_request_body()
                result = service.run_project_package_preflight()
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "ok" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/project/package/build":
            try:
                payload = self._read_json_request_body()
                mode = payload.get("mode")
                source_of_truth = payload.get("source_of_truth")
                output_path = payload.get("output_path")
                if not isinstance(mode, str) or not mode.strip():
                    raise ValueError("field must be a non-empty string: mode")
                if not isinstance(source_of_truth, str) or not source_of_truth.strip():
                    raise ValueError("field must be a non-empty string: source_of_truth")
                if output_path is not None and not isinstance(output_path, str):
                    raise ValueError("field must be a string when provided: output_path")
                result = service.build_project_package(
                    mode=mode,
                    source_of_truth=source_of_truth,
                    output_path=output_path,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "built" else HTTPStatus.BAD_REQUEST
            response_payload = dict(result)
            if result["status"] != "built":
                response_payload.update(
                    {
                        "error": "project_package_build_failed",
                        "message": "project package build failed",
                    }
                )
            self._write_json(status_code, response_payload)
            return

        if self.path == "/api/workbench/project/package/load":
            try:
                payload = self._read_json_request_body()
                package_path = payload.get("package_path")
                if not isinstance(package_path, str) or not package_path.strip():
                    raise ValueError("field must be a non-empty string: package_path")
                result = service.load_project_package(package_path=package_path)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/package/unload":
            try:
                self._read_json_request_body()
                result = service.unload_project_package()
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/package/external-resources/bind":
            try:
                payload = self._read_json_request_body()
                resource_id = payload.get("resource_id")
                value = payload.get("value")
                if not isinstance(resource_id, str) or not resource_id.strip():
                    raise ValueError("field must be a non-empty string: resource_id")
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("field must be a non-empty string: value")
                result = service.bind_loaded_package_external_resource(
                    resource_id=resource_id,
                    value=value,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/security/enable-required":
            try:
                payload = self._read_json_request_body()
                confirm_high_risk = payload.get("confirm_high_risk", False)
                if not isinstance(confirm_high_risk, bool):
                    raise ValueError("field must be a boolean when provided: confirm_high_risk")
                result = service.enable_project_required_security_settings(
                    confirm_high_risk=confirm_high_risk,
                )
            except HighRiskConfigurationChangeRequiredError as exc:
                self._write_high_risk_configuration_confirmation_required_error(exc)
                return
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/update/check":
            try:
                payload = self._read_json_request_body()
                force = payload.get("force", False)
                if not isinstance(force, bool):
                    raise ValueError("field must be a boolean when provided: force")
                result = self._get_update_service().check_for_updates(force=force)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/open":
            try:
                payload = self._read_json_request_body()
                project_path = payload.get("project_path")
                if not isinstance(project_path, str):
                    raise ValueError("field must be a string: project_path")
                result = service.open_project(project_path=project_path)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "project": result["project"],
                    "graph_document": result["graph_document"].model_dump(),
                },
            )
            return

        if self.path == "/api/workbench/project/graph-upgrade/apply":
            try:
                payload = self._read_json_request_body()
                decision = payload.get("decision")
                if not isinstance(decision, str) or not decision.strip():
                    raise ValueError("field must be a non-empty string: decision")
                result = service.apply_pending_graph_upgrade(decision=decision.strip())
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "project": result["project"],
                    "graph_document": result["graph_document"].model_dump(),
                },
            )
            return

        if self.path == "/api/workbench/project/graph-upgrade/recheck":
            try:
                self._read_json_request_body()
                result = service.recheck_pending_graph_upgrade()
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "project": result["project"],
                    "pending_graph_upgrade": result["pending_graph_upgrade"],
                },
            )
            return

        if self.path == "/api/workbench/project/convert-webcontrol":
            try:
                payload = self._read_json_request_body()
                source_path = payload.get("source_path")
                output_project_path = payload.get("output_project_path")
                if not isinstance(source_path, str) or not source_path.strip():
                    raise ValueError("field must be a non-empty string: source_path")
                if not isinstance(output_project_path, str) or not output_project_path.strip():
                    raise ValueError("field must be a non-empty string: output_project_path")
                blueprint_paths = payload.get("blueprint_paths")
                if blueprint_paths is not None and (
                    not isinstance(blueprint_paths, list)
                    or any(not isinstance(item, str) or not item.strip() for item in blueprint_paths)
                ):
                    raise ValueError("field must be a non-empty string list when provided: blueprint_paths")
                blueprint_directory = payload.get("blueprint_directory")
                if blueprint_directory is not None and not isinstance(blueprint_directory, str):
                    raise ValueError("field must be a string when provided: blueprint_directory")
                project_name = payload.get("project_name")
                if project_name is not None and not isinstance(project_name, str):
                    raise ValueError("field must be a string when provided: project_name")
                overwrite_output = payload.get("overwrite_output", False)
                auto_open_project = payload.get("auto_open_project", False)
                preserve_legacy_metadata = payload.get("preserve_legacy_metadata", True)
                write_conversion_report = payload.get("write_conversion_report", True)
                for field_name, field_value in {
                    "overwrite_output": overwrite_output,
                    "auto_open_project": auto_open_project,
                    "preserve_legacy_metadata": preserve_legacy_metadata,
                    "write_conversion_report": write_conversion_report,
                }.items():
                    if not isinstance(field_value, bool):
                        raise ValueError(f"field must be a boolean when provided: {field_name}")
                result = service.convert_webcontrol_project(
                    source_path=source_path.strip(),
                    blueprint_paths=blueprint_paths,
                    blueprint_directory=blueprint_directory,
                    output_project_path=output_project_path.strip(),
                    project_name=project_name,
                    overwrite_output=overwrite_output,
                    auto_open_project=auto_open_project,
                    preserve_legacy_metadata=preserve_legacy_metadata,
                    write_conversion_report=write_conversion_report,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, self._serialize_converter_result(result))
            return

        if self.path == "/api/workbench/project/save":
            try:
                payload = self._read_json_request_body()
                result = service.save_project(
                    graph_document_payload=self._extract_optional_graph_document_payload(
                        payload,
                        allow_bare_payload=False,
                    )
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "project": result["project"],
                    "graph_document": result["graph_document"].model_dump(),
                },
            )
            return

        if self.path == "/api/workbench/project/save-as":
            try:
                payload = self._read_json_request_body()
                project_path = payload.get("project_path")
                if not isinstance(project_path, str):
                    raise ValueError("field must be a string: project_path")
                result = service.save_project_as(
                    project_path=project_path,
                    graph_document_payload=self._extract_optional_graph_document_payload(
                        payload,
                        allow_bare_payload=False,
                    ),
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "project": result["project"],
                    "graph_document": result["graph_document"].model_dump(),
                },
            )
            return

        if self.path == "/api/workbench/recent-projects/remove":
            try:
                payload = self._read_json_request_body()
                project_path = payload.get("project_path")
                if not isinstance(project_path, str):
                    raise ValueError("field must be a string: project_path")
                result = service.remove_recent_project(project_path=project_path)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "recent_projects": result["recent_projects"],
                },
            )
            return

        if self.path == "/api/workbench/resources/user-components":
            try:
                payload = self._read_json_request_body()
                resource_name = payload.get("resource_name")
                if not isinstance(resource_name, str):
                    raise ValueError("field must be a string: resource_name")
                tags = payload.get("tags")
                if tags is not None and not isinstance(tags, list):
                    raise ValueError("field must be an array when provided: tags")
                replace_existing_resource_id = payload.get("replace_existing_resource_id")
                if replace_existing_resource_id is not None and not isinstance(
                    replace_existing_resource_id, str
                ):
                    raise ValueError("field must be a string when provided: replace_existing_resource_id")
                result = service.save_user_component_resource(
                    resource_name=resource_name,
                    replace_existing_resource_id=replace_existing_resource_id,
                )
                if tags is not None:
                    result = service.update_resource_tags(
                        resource_id=result["resource"]["resource_id"],
                        tags=tags,
                    )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/subgraphs":
            try:
                payload = self._read_json_request_body()
                resource_name = payload.get("resource_name")
                if not isinstance(resource_name, str):
                    raise ValueError("field must be a string: resource_name")
                tags = payload.get("tags")
                if tags is not None and not isinstance(tags, list):
                    raise ValueError("field must be an array when provided: tags")
                replace_existing_resource_id = payload.get("replace_existing_resource_id")
                if replace_existing_resource_id is not None and not isinstance(
                    replace_existing_resource_id, str
                ):
                    raise ValueError(
                        "field must be a string when provided: replace_existing_resource_id"
                    )
                result = service.save_subgraph_resource(
                    resource_name=resource_name,
                    replace_existing_resource_id=replace_existing_resource_id,
                )
                if tags is not None:
                    result = service.update_resource_tags(
                        resource_id=result["resource"]["resource_id"],
                        tags=tags,
                    )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/custom-node-graphs":
            try:
                payload = self._read_json_request_body()
                resource_name = payload.get("resource_name")
                if not isinstance(resource_name, str):
                    raise ValueError("field must be a string: resource_name")
                tags = payload.get("tags")
                if tags is not None and not isinstance(tags, list):
                    raise ValueError("field must be an array when provided: tags")
                replace_existing_resource_id = payload.get("replace_existing_resource_id")
                if replace_existing_resource_id is not None and not isinstance(
                    replace_existing_resource_id, str
                ):
                    raise ValueError(
                        "field must be a string when provided: replace_existing_resource_id"
                    )
                result = service.save_custom_node_graph_resource(
                    resource_name=resource_name,
                    replace_existing_resource_id=replace_existing_resource_id,
                )
                if tags is not None:
                    result = service.update_resource_tags(
                        resource_id=result["resource"]["resource_id"],
                        tags=tags,
                    )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/export":
            try:
                payload = self._read_json_request_body()
                resource_id = payload.get("resource_id")
                export_path = payload.get("export_path")
                if not isinstance(resource_id, str):
                    raise ValueError("field must be a string: resource_id")
                if not isinstance(export_path, str):
                    raise ValueError("field must be a string: export_path")
                result = service.export_resource(resource_id=resource_id, export_path=export_path)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "resource": result["resource"],
                    "export_path": result["export_path"],
                },
            )
            return

        if self.path == "/api/workbench/resources/import":
            try:
                payload = self._read_json_request_body()
                import_path = payload.get("import_path")
                replace_existing = payload.get("replace_existing", False)
                if not isinstance(import_path, str):
                    raise ValueError("field must be a string: import_path")
                if not isinstance(replace_existing, bool):
                    raise ValueError("field must be a boolean when provided: replace_existing")
                result = service.import_resource(
                    import_path=import_path,
                    replace_existing=replace_existing,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/graph/source-projection":
            try:
                payload = self._read_json_request_body()
                target_source_kind = payload.get("target_source_kind", "native_flow")
                if not isinstance(target_source_kind, str):
                    raise ValueError("field must be a string when provided: target_source_kind")
                graph_document_payload = payload.get("graph_document")
                if graph_document_payload is not None and not isinstance(graph_document_payload, dict):
                    raise ValueError("field must be a JSON object when provided: graph_document")
                result = service.get_graph_source_projection_document(
                    target_source_kind=target_source_kind,
                    graph_document_payload=graph_document_payload,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "ready" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/editor/history/record":
            try:
                payload = self._read_json_request_body()
                operation_kind = payload.get("operation_kind")
                label = payload.get("label")
                operation_payload = payload.get("payload")
                if not isinstance(operation_kind, str):
                    raise ValueError("field must be a string: operation_kind")
                if not isinstance(label, str):
                    raise ValueError("field must be a string: label")
                result = service.record_editor_operation(
                    operation_kind=operation_kind,
                    label=label,
                    payload=operation_payload,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "operation": result["operation"],
                    "history": result["history"],
                },
            )
            return

        if self.path.startswith("/api/workbench/runtime/") and self.path.endswith("/run"):
            try:
                self._read_json_request_body()
                session_id = self.path.removeprefix("/api/workbench/runtime/").removesuffix("/run")
                if not session_id:
                    raise ValueError("session_id must not be empty")
                result = service.run_runtime_session(session_id=session_id)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK if result["status"] == "completed" else HTTPStatus.BAD_REQUEST
            )
            response_payload = dict(result)
            if result["status"] != "completed":
                response_payload.update(
                    self._build_runtime_failure_error_payload(
                        result,
                        error_code="runtime_run_failed",
                    )
                )
            self._write_json(status_code, response_payload)
            return

        if self.path.startswith("/api/workbench/resources/") and self.path.endswith("/enabled"):
            try:
                payload = self._read_json_request_body()
                enabled = payload.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("field must be a boolean: enabled")
                resource_id = self.path.removeprefix("/api/workbench/resources/").removesuffix(
                    "/enabled"
                )
                if not resource_id:
                    raise ValueError("resource_id must not be empty")
                result = service.set_resource_enabled(resource_id=resource_id, enabled=enabled)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path.startswith("/api/workbench/resources/") and self.path.endswith("/tags"):
            try:
                payload = self._read_json_request_body()
                tags = payload.get("tags")
                if not isinstance(tags, list):
                    raise ValueError("field must be an array: tags")
                resource_id = self.path.removeprefix("/api/workbench/resources/").removesuffix(
                    "/tags"
                )
                if not resource_id:
                    raise ValueError("resource_id must not be empty")
                result = service.update_resource_tags(resource_id=resource_id, tags=tags)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/custom-node-graphs/create-empty":
            try:
                payload = self._read_json_request_body()
                resource_name = payload.get("resource_name")
                if not isinstance(resource_name, str):
                    raise ValueError("field must be a string: resource_name")
                result = service.create_empty_custom_node_graph_resource(
                    resource_name=resource_name,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/delete":
            try:
                payload = self._read_json_request_body()
                resource_id = payload.get("resource_id")
                if not isinstance(resource_id, str) or not resource_id.strip():
                    raise ValueError("field must be a non-empty string: resource_id")
                result = service.delete_resource(resource_id=resource_id.strip())
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/metadata":
            try:
                payload = self._read_json_request_body()
                resource_id = payload.get("resource_id")
                if not isinstance(resource_id, str) or not resource_id.strip():
                    raise ValueError("field must be a non-empty string: resource_id")
                display_name = payload.get("display_name")
                if not isinstance(display_name, str) or not display_name.strip():
                    raise ValueError("field must be a non-empty string: display_name")
                description = payload.get("description")
                if description is not None and not isinstance(description, str):
                    raise ValueError("field must be a string when provided: description")
                display_name_i18n = payload.get("display_name_i18n")
                if display_name_i18n is not None and not isinstance(display_name_i18n, dict):
                    raise ValueError("field must be an object when provided: display_name_i18n")
                description_i18n = payload.get("description_i18n")
                if description_i18n is not None and not isinstance(description_i18n, dict):
                    raise ValueError("field must be an object when provided: description_i18n")
                result = service.update_resource_metadata(
                    resource_id=resource_id.strip(),
                    display_name=display_name.strip(),
                    description=description,
                    display_name_i18n=display_name_i18n,
                    description_i18n=description_i18n,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/rename":
            try:
                payload = self._read_json_request_body()
                resource_id = payload.get("resource_id")
                if not isinstance(resource_id, str) or not resource_id.strip():
                    raise ValueError("field must be a non-empty string: resource_id")
                display_name = payload.get("display_name")
                if not isinstance(display_name, str) or not display_name.strip():
                    raise ValueError("field must be a non-empty string: display_name")
                result = service.rename_resource(
                    resource_id=resource_id.strip(),
                    display_name=display_name.strip(),
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        self._write_not_found_error()

    def do_PUT(self) -> None:  # noqa: N802
        if self._handle_external_api(method="PUT"):
            return
        if not self._require_api_token():
            return
        try:
            service = self._get_service()
        except ValueError as exc:
            self._write_workspace_state_error(exc)
            return
        if self.path == "/api/workbench/graph":
            try:
                payload = self._read_json_request_body()
                expected_revision = payload.pop("expected_graph_document_save_revision", None)
                if expected_revision is not None and not isinstance(expected_revision, int):
                    raise ValueError(
                        "field must be an integer when provided: expected_graph_document_save_revision"
                    )
                result = service.save_graph_document(
                    payload,
                    expected_graph_document_save_revision=expected_revision,
                )
            except GraphDocumentRevisionConflictError as exc:
                self._write_graph_revision_conflict_error(exc)
                return
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "graph_model": result["graph_model"].model_dump(),
                    "view": result["view"],
                },
            )
            return

        self._write_not_found_error()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _write_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_not_found_error(self) -> None:
        sanitized_path = _sanitize_path_for_error(self.path)
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {
                "error": "not_found",
                "path": sanitized_path,
                "message": f"resource not found: {sanitized_path}",
            },
        )

    def _write_workspace_state_error(self, exc: ValueError) -> None:
        self._write_json(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {
                "error": "workspace_state_invalid",
                "message": str(exc),
            },
        )

    def _write_invalid_request_error(self, exc: ValueError) -> None:
        payload = {
            "error": getattr(exc, "error_code", "invalid_request"),
            "message": str(exc),
        }
        recovery_action = getattr(exc, "recovery_action", None)
        if recovery_action is not None:
            payload["recovery_action"] = recovery_action
        details = getattr(exc, "details", None)
        if isinstance(details, dict):
            payload["details"] = details
        self._write_json(
            HTTPStatus.BAD_REQUEST,
            payload,
        )

    def _write_high_risk_configuration_confirmation_required_error(
        self,
        exc: HighRiskConfigurationChangeRequiredError,
    ) -> None:
        self._write_json(
            HTTPStatus.CONFLICT,
            {
                "error": "high_risk_confirmation_required",
                "message": str(exc),
                "scope": exc.scope,
                "requires_confirmation": True,
                "high_risk_changes": [dict(item) for item in exc.high_risk_changes],
            },
        )

    def _write_host_file_dialog_unavailable_error(self) -> None:
        self._write_json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "host.file_dialog_unavailable",
                "message": "host file dialog is unavailable",
            },
        )

    def _write_host_open_path_unavailable_error(self) -> None:
        self._write_json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "host.open_path_unavailable",
                "message": "host open path is unavailable",
            },
        )

    def _write_graph_revision_conflict_error(
        self,
        exc: GraphDocumentRevisionConflictError,
    ) -> None:
        self._write_json(
            HTTPStatus.CONFLICT,
            {
                "error": "graph_revision_conflict",
                "message": str(exc),
            },
        )

    def _build_compile_failure_error_payload(
        self,
        result: dict,
        *,
        error_code: str,
    ) -> dict:
        view = result.get("view", {})
        primary_diagnostic = view.get("primary_diagnostic")
        message = "compile failed"
        if isinstance(primary_diagnostic, dict):
            primary_message = primary_diagnostic.get("message")
            if isinstance(primary_message, str) and primary_message.strip():
                message = primary_message
        details = {
            "primary_diagnostic": primary_diagnostic,
            "diagnostic_summary": view.get("diagnostic_summary"),
            "stage_overview": view.get("stage_overview"),
        }
        return {
            "error": error_code,
            "message": message,
            "details": details,
        }

    def _build_runtime_failure_error_payload(
        self,
        result: dict,
        *,
        error_code: str,
    ) -> dict:
        diagnostics = result.get("diagnostics")
        message = "runtime failed"
        details = None
        if isinstance(diagnostics, dict):
            entries = diagnostics.get("entries")
            primary_entry = None
            if isinstance(entries, list) and entries:
                severity_rank = {
                    "info": 0,
                    "warning": 1,
                    "degraded": 2,
                    "error": 3,
                    "fatal": 4,
                }
                typed_entries = [item for item in entries if isinstance(item, dict)]
                if typed_entries:
                    primary_entry = max(
                        typed_entries,
                        key=lambda item: severity_rank.get(item.get("severity"), -1),
                    )
                    primary_message = primary_entry.get("message")
                    if isinstance(primary_message, str) and primary_message.strip():
                        message = primary_message
            details = {
                "primary_diagnostic": primary_entry,
                "diagnostic_summary": {
                    "total_count": diagnostics.get("total_count"),
                    "highest_severity": diagnostics.get("highest_severity"),
                },
            }
        result_payload = result.get("result")
        if message == "runtime failed" and isinstance(result_payload, dict):
            failure_reason = result_payload.get("failure_reason")
            if isinstance(failure_reason, str) and failure_reason.strip():
                message = failure_reason
        return {
            "error": error_code,
            "message": message,
            "details": details,
            "runtime_session": result.get("runtime_session"),
            "runtime_plan": result.get("runtime_plan"),
            "node_states": result.get("node_states", []),
            "event_log": result.get("event_log", []),
            "diagnostics": diagnostics,
            "result": result_payload if isinstance(result_payload, dict) else result.get("result"),
        }

    def _serialize_request(self, request) -> dict:
        if hasattr(request, "model_dump"):
            return request.model_dump()
        return dict(request)

    def _serialize_converter_result(self, result: dict) -> dict:
        payload = dict(result)
        graph_document = payload.get("graph_document")
        if hasattr(graph_document, "model_dump"):
            payload["graph_document"] = graph_document.model_dump(mode="json")
        return payload

    def _get_optional_query_param(self, params: dict[str, list[str]], key: str) -> str | None:
        values = params.get(key)
        if not values:
            return None
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _get_multi_query_param(self, params: dict[str, list[str]], key: str) -> list[str]:
        values = params.get(key, [])
        normalized: list[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            parts = [item.strip() for item in value.split(",")]
            normalized.extend([item for item in parts if item])
        return normalized

    def _get_optional_bool_query_param(
        self,
        params: dict[str, list[str]],
        key: str,
    ) -> bool | None:
        value = self._get_optional_query_param(params, key)
        if value is None:
            return None
        if value.lower() in {"true", "1", "yes", "on"}:
            return True
        if value.lower() in {"false", "0", "no", "off"}:
            return False
        return None

    def _get_optional_float_query_param(
        self,
        params: dict[str, list[str]],
        key: str,
    ) -> float | None:
        value = self._get_optional_query_param(params, key)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"query parameter must be numeric when provided: {key}") from None

    def _handle_host_file_dialog(self) -> None:
        try:
            payload = self._read_json_request_body()
            self._validate_host_file_dialog_payload(payload)
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return

        provider = getattr(self.server, "file_dialog_provider", None)
        if provider is None:
            self._write_host_file_dialog_unavailable_error()
            return

        try:
            result = provider(payload)
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return
        except RuntimeError as exc:
            self._write_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "host.file_dialog_unavailable",
                    "message": str(exc) or "host file dialog is unavailable",
                },
            )
            return

        if not isinstance(result, dict):
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "host.file_dialog_invalid_response",
                    "message": "host file dialog provider must return a JSON object",
                },
            )
            return
        self._write_json(HTTPStatus.OK, result)

    def _validate_host_file_dialog_payload(self, payload: dict) -> None:
        mode = payload.get("mode")
        allowed_modes = {"open_file", "open_files", "open_folder", "save_file"}
        if mode not in allowed_modes:
            raise ValueError(
                "field must be one of open_file, open_files, open_folder, save_file: mode"
            )
        title = payload.get("title")
        if title is not None and not isinstance(title, str):
            raise ValueError("field must be a string when provided: title")
        default_path = payload.get("default_path")
        if default_path is not None and not isinstance(default_path, str):
            raise ValueError("field must be a string when provided: default_path")
        file_types = payload.get("file_types")
        if file_types is not None and (
            not isinstance(file_types, list)
            or any(not isinstance(item, str) for item in file_types)
        ):
            raise ValueError("field must be a string list when provided: file_types")

    def _handle_host_open_path(self) -> None:
        try:
            payload = self._read_json_request_body()
            resolved_path = self._validate_host_open_path_payload(payload)
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return

        provider = getattr(self.server, "open_path_provider", None)
        if provider is None:
            self._write_host_open_path_unavailable_error()
            return

        provider_payload = {
            "path": str(resolved_path),
            "target_kind": "directory" if resolved_path.is_dir() else "file",
        }
        try:
            result = provider(provider_payload)
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return
        except RuntimeError as exc:
            self._write_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "host.open_path_unavailable",
                    "message": str(exc) or "host open path is unavailable",
                },
            )
            return

        if not isinstance(result, dict):
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "host.open_path_invalid_response",
                    "message": "host open path provider must return a JSON object",
                },
            )
            return
        self._write_json(HTTPStatus.OK, result)

    def _validate_host_open_path_payload(self, payload: dict) -> Path:
        raw_path = payload.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("field must be a non-empty string: path")
        resolved_path = Path(raw_path).expanduser().resolve()
        if not resolved_path.exists():
            exc = ValueError("path does not exist")
            exc.error_code = "host.open_path_missing"
            raise exc
        return resolved_path

    def _handle_host_read_file(self) -> None:
        try:
            payload = self._read_json_request_body()
            path, encoding, max_bytes = self._validate_host_read_file_payload(payload)
            resolved_path = path.expanduser().resolve()
            allowed_roots = self._collect_host_read_roots()
            if not any(_is_path_under_root(resolved_path, root) for root in allowed_roots):
                self._write_json(
                    HTTPStatus.FORBIDDEN,
                    {
                        "error": "forbidden",
                        "message": (
                            f"file path is not within any allowed directory: {resolved_path}"
                        ),
                    },
                )
                return
            if not resolved_path.is_file():
                exc = ValueError("path must point to a regular file")
                exc.error_code = "host.read_file_not_file"
                raise exc
            file_size = resolved_path.stat().st_size
            if file_size > max_bytes:
                exc = ValueError(f"file is too large: {file_size} bytes")
                exc.error_code = "host.read_file_too_large"
                raise exc
            raw_content = resolved_path.read_bytes()
            try:
                content = raw_content.decode(encoding)
            except UnicodeDecodeError as decode_exc:
                exc = ValueError(f"file cannot be decoded with {encoding}")
                exc.error_code = "host.read_file_decode_failed"
                raise exc from decode_exc
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return
        except OSError as exc:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "host.read_file_failed",
                    "message": str(exc),
                },
            )
            return

        self._write_json(
            HTTPStatus.OK,
            {
                "status": "read",
                "path": str(resolved_path),
                "encoding": encoding,
                "content": content,
                "bytes_read": len(raw_content),
            },
        )

    def _validate_host_read_file_payload(self, payload: dict) -> tuple[Path, str, int]:
        raw_path = payload.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("field must be a non-empty string: path")
        encoding = payload.get("encoding", "utf-8")
        if not isinstance(encoding, str) or not encoding.strip():
            raise ValueError("field must be a non-empty string when provided: encoding")
        max_bytes_value = payload.get("max_bytes", 2 * 1024 * 1024)
        if not isinstance(max_bytes_value, int) or max_bytes_value <= 0:
            raise ValueError("field must be a positive integer when provided: max_bytes")
        return Path(raw_path), encoding.strip(), max_bytes_value

    def _collect_host_read_roots(self) -> tuple[Path, ...]:
        roots: list[Path] = []
        workspace_state_path = self._resolve_workspace_state_path().resolve()
        workspace_root = workspace_state_path.parent
        roots.append(workspace_root)
        ui_root = self._resolve_ui_dist_path().resolve()
        roots.append(ui_root)
        try:
            service = self._get_service()
        except ValueError:
            service = None
        if service is not None:
            project_document = service.get_project_document()
            project_file_path = project_document.get("project", {}).get("project_file_path")
            if isinstance(project_file_path, str) and project_file_path.strip():
                project_root = Path(project_file_path).resolve().parent
                if project_root not in roots:
                    roots.append(project_root)
        return tuple(dict.fromkeys(roots))

    def _try_serve_ui_asset(self) -> bool:
        request_path = unquote(urlparse(self.path).path)
        if request_path.startswith("/api/"):
            return False
        ui_dist_path = self._resolve_ui_dist_path()
        index_path = ui_dist_path / "index.html"
        if not index_path.exists():
            return False

        relative_path = request_path.lstrip("/")
        if request_path in {"", "/"}:
            return self._write_file_response(index_path, content_type="text/html; charset=utf-8")

        requested_file = (ui_dist_path / relative_path).resolve()
        try:
            requested_file.relative_to(ui_dist_path.resolve())
        except ValueError:
            return False

        if requested_file.is_file():
            content_type, _ = mimetypes.guess_type(str(requested_file))
            return self._write_file_response(
                requested_file,
                content_type=content_type or "application/octet-stream",
            )

        if "." not in Path(relative_path).name:
            return self._write_file_response(index_path, content_type="text/html; charset=utf-8")

        return False

    def _write_file_response(self, path: Path, *, content_type: str) -> bool:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _write_runtime_stream(
        self,
        service: CompilationWorkbenchService,
        session_id: str,
    ) -> None:
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        initial_snapshot = service.get_runtime_stream_snapshot(session_id=session_id)
        self._write_sse_event("runtime.snapshot", initial_snapshot)
        initial_status = initial_snapshot.get("status")
        if initial_status == "completed":
            self._write_sse_event(
                "runtime.summary",
                {
                    "session_id": initial_snapshot.get("session_id"),
                    "status": initial_snapshot.get("status"),
                    "total_node_count": len(initial_snapshot.get("node_states", [])),
                    "completed_node_count": initial_snapshot.get("execution_summary", {}).get("completed_node_count", 0),
                    "failed_node_count": initial_snapshot.get("execution_summary", {}).get("failed_node_count", 0),
                    "running_node_count": 0,
                    "pending_node_count": 0,
                    "percent": 100.0,
                    "event_count": initial_snapshot.get("execution_summary", {}).get("event_count", 0),
                },
            )
            self._write_sse_event("runtime.completed", initial_snapshot)
            return
        if initial_status == "failed":
            total_node_count = len(initial_snapshot.get("node_states", []))
            failed_count = initial_snapshot.get("execution_summary", {}).get("failed_node_count", 0)
            completed_count = initial_snapshot.get("execution_summary", {}).get("completed_node_count", 0)
            pending_count = max(total_node_count - completed_count - failed_count, 0)
            percent = ((completed_count + failed_count) / total_node_count * 100.0) if total_node_count else 0.0
            self._write_sse_event(
                "runtime.summary",
                {
                    "session_id": initial_snapshot.get("session_id"),
                    "status": initial_snapshot.get("status"),
                    "total_node_count": total_node_count,
                    "completed_node_count": completed_count,
                    "failed_node_count": failed_count,
                    "running_node_count": 0,
                    "pending_node_count": pending_count,
                    "percent": round(percent, 1),
                    "event_count": initial_snapshot.get("execution_summary", {}).get("event_count", 0),
                },
            )
            self._write_sse_event("runtime.failed", initial_snapshot)
            return
        for event_name, payload in service.iter_runtime_stream_events(session_id=session_id):
            if event_name == "runtime.snapshot":
                continue
            self._write_sse_event(event_name, payload)
            if event_name in {"runtime.completed", "runtime.failed", "runtime.aborted"}:
                break

    def _write_sse_event(self, event_name: str, payload: dict) -> None:
        body = (
            f"event: {event_name}\n"
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        ).encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def _handle_startup_diagnostics(self) -> None:
        report = build_startup_diagnostics(
            self._resolve_preferences_path(),
            self._resolve_workspace_state_path(),
        )
        report["ui_hosting"] = self._build_ui_hosting_metadata()
        self._write_json(HTTPStatus.OK, report)

    def _handle_startup_recover(self) -> None:
        try:
            payload = self._read_optional_json_request_body() or {}
            targets = payload.get("targets")
            preferences_path = self._resolve_preferences_path()
            workspace_state_path = self._resolve_workspace_state_path()
            if targets is None:
                # No explicit targets: recover everything the diagnostics flagged.
                report = build_startup_diagnostics(
                    preferences_path, workspace_state_path
                )
                targets = report["recoverable_targets"]
            if not isinstance(targets, list) or not all(
                isinstance(target, str) for target in targets
            ):
                raise ValueError("field must be a list of strings when provided: targets")
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return

        results: list[dict] = []
        try:
            for target in targets:
                results.append(
                    recover_startup_target(
                        target, preferences_path, workspace_state_path
                    )
                )
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return
        except OSError as exc:
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "startup_recovery_failed",
                    "message": f"恢复操作失败: {exc}",
                    "results": results,
                },
            )
            return

        self._write_json(
            HTTPStatus.OK,
            {"status": "recovered", "results": results},
        )

    def _write_degraded_health(self, exc: ValueError) -> None:
        self._write_json(
            HTTPStatus.OK,
            {
                "status": "degraded",
                "service": "weconduct-api",
                "message": str(exc),
                "startup_diagnostics": build_startup_diagnostics(
                    self._resolve_preferences_path(),
                    self._resolve_workspace_state_path(),
                ),
                "ui_hosting": self._build_ui_hosting_metadata(),
            },
        )

    def _read_json_request_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _read_optional_json_request_body(self) -> dict | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        if not raw_body.strip():
            return None
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        if payload == {}:
            return None
        return payload

    def _extract_optional_graph_document_payload(
        self,
        payload: dict | None,
        *,
        allow_bare_payload: bool = True,
    ) -> dict | None:
        if payload is None:
            return None
        if "graph_document" not in payload:
            return payload if allow_bare_payload else None
        graph_document_payload = payload.get("graph_document")
        if graph_document_payload is None:
            return None
        if not isinstance(graph_document_payload, dict):
            raise ValueError("field must be a JSON object when provided: graph_document")
        return graph_document_payload

    def _validate_compile_payload(self, payload: dict) -> None:
        required_fields = ("source_kind", "entry_document", "source_text")
        for field_name in required_fields:
            if field_name not in payload:
                raise ValueError(f"missing required field: {field_name}")
        for field_name in ("source_kind", "entry_document"):
            field_value = payload[field_name]
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f"field must be a non-empty string: {field_name}")
        if not isinstance(payload["source_text"], str):
            raise ValueError("field must be a string: source_text")

    def _get_service(self) -> CompilationWorkbenchService:
        with self.server._service_lock:
            if not hasattr(self.server, "workbench_service"):
                self.server.workbench_service = CompilationWorkbenchService(
                    state_store=FileWorkspaceStateStore(self._resolve_workspace_state_path()),
                    configuration_service=self._get_configuration_service(),
                )
            return self.server.workbench_service

    def _get_configuration_service(self) -> ConfigurationService:
        with self.server._service_lock:
            if not hasattr(self.server, "configuration_service"):
                repository = FileProgramConfigurationRepository(
                    self._resolve_preferences_path()
                )
                registry = build_builtin_configuration_registry()
                legacy_preferences = repository.read_legacy_payload()
                self.server.configuration_migration_result = migrate_program_configuration(
                    repository=repository,
                    registry=registry,
                )
                graph_repository = FileGraphConfigurationRepository(
                    self._resolve_preferences_path().with_name("graph-preferences.json")
                )
                self.server.graph_configuration_migration_result = migrate_graph_configuration(
                    repository=graph_repository,
                    registry=registry,
                    legacy_preferences=legacy_preferences,
                )
                graph_configuration_repository = WorkbenchGraphConfigurationRepository(
                    editor_repository=graph_repository,
                    get_entrypoint_runtime=lambda: (
                        self.server.workbench_service.get_graph_entrypoint_runtime_configuration()
                        if hasattr(self.server, "workbench_service")
                        else {}
                    ),
                    update_entrypoint_runtime=lambda values: self._get_service().update_graph_entrypoint_runtime_configuration(values),
                )
                self.server.configuration_service = ConfigurationService(
                    registry=registry,
                    repositories={
                        "program": repository,
                        "graph": graph_configuration_repository,
                        "project": ProjectConfigurationRepository(
                            lambda: self._get_service().get_project_settings_document()["project_settings"],
                            lambda document: self._get_service().update_project_settings(project_settings=document),
                        ),
                    },
                )
            return self.server.configuration_service

    def _get_external_api_preferences_summary(self) -> dict:
        values = self._get_configuration_service().get_values(scope="program")["values"]
        security = values.get("security")
        if not isinstance(security, dict):
            raise ValueError("program security configuration is invalid")
        roots = security.get("external_api_project_allowed_roots", [])
        if not isinstance(roots, list):
            raise ValueError("external API project allowed roots configuration is invalid")
        return {
            "enabled": bool(security.get("external_api_enabled", False)),
            "token_configured": bool(security.get("external_api_token")),
            "project_allowed_roots": list(roots),
        }

    def _update_external_api_preferences(self, payload: dict) -> dict:
        enabled = payload.get("enabled")
        token = payload.get("token")
        clear_token = payload.get("clear_token", False)
        project_allowed_roots = payload.get("project_allowed_roots")
        confirm_high_risk = payload.get("confirm_high_risk", False)
        if not isinstance(enabled, bool):
            raise ValueError("field must be a boolean: enabled")
        if token is not None and (not isinstance(token, str) or not token.strip()):
            raise ValueError("field must be a non-empty string when provided: token")
        if not isinstance(clear_token, bool):
            raise ValueError("field must be a boolean: clear_token")
        if token is not None and clear_token:
            raise ValueError("token and clear_token cannot be provided together")
        if not isinstance(project_allowed_roots, list) or any(
            not isinstance(root, str) or not root.strip() for root in project_allowed_roots
        ):
            raise ValueError("field must be a string list: project_allowed_roots")
        if not isinstance(confirm_high_risk, bool):
            raise ValueError("field must be a boolean: confirm_high_risk")

        normalized_roots = list(
            dict.fromkeys(
                str(Path(root).expanduser().resolve()) for root in project_allowed_roots
            )
        )
        configuration_service = self._get_configuration_service()
        values = configuration_service.get_values(scope="program")["values"]
        security = values.get("security")
        if not isinstance(security, dict):
            raise ValueError("program security configuration is invalid")
        current_token = security.get("external_api_token")
        effective_token = (
            token.strip()
            if isinstance(token, str)
            else None
            if clear_token
            else current_token
        )
        if enabled and not isinstance(effective_token, str):
            raise ValueError("a token is required when enabling the external API")

        requested_values = {
            "external_api_enabled": enabled,
            "external_api_token": effective_token,
            "external_api_project_allowed_roots": normalized_roots,
        }
        operations = [
            {"op": "replace", "path": f"/security/{key}", "value": value}
            for key, value in requested_values.items()
            if security.get(key) != value
        ]
        configuration_service.apply(
            scope="program",
            operations=operations,
            confirm_high_risk=confirm_high_risk,
        )
        self.server.external_api_enabled = enabled
        self.server.external_api_token = effective_token if isinstance(effective_token, str) else None
        self.server.external_api_project_allowed_roots = tuple(
            Path(root) for root in normalized_roots
        )
        return {
            "enabled": enabled,
            "token_configured": bool(effective_token),
            "project_allowed_roots": normalized_roots,
        }

    def _get_update_service(self) -> UpdateService:
        if not hasattr(self.server, "update_service"):
            from weconduct.application.compilation_workbench_service import CURRENT_API_VERSION

            self.server.update_service = UpdateService(
                current_version=CURRENT_API_VERSION,
                repository="HalcyonAlcedo/WeConduct",
            )
        return self.server.update_service

    def _resolve_workspace_state_path(self) -> Path:
        configured_path = getattr(self.server, "workspace_state_path", None)
        if configured_path is None:
            return DEFAULT_WORKSPACE_STATE_PATH
        return Path(configured_path)

    def _resolve_ui_dist_path(self) -> Path:
        configured_path = getattr(self.server, "ui_dist_path", None)
        if configured_path is None:
            return DEFAULT_UI_DIST_PATH
        return Path(configured_path)

    def _resolve_preferences_path(self) -> Path:
        configured_path = getattr(self.server, "preferences_path", None)
        if configured_path is None:
            return DEFAULT_PREFERENCES_PATH
        return Path(configured_path)

    def _build_ui_hosting_metadata(self) -> dict:
        ui_dist_path = self._resolve_ui_dist_path().resolve()
        index_path = ui_dist_path / "index.html"
        ui_dist_available = index_path.exists()
        ui_mode = getattr(self.server, "ui_mode", "desktop_shell")
        return {
            "ui_hosted": ui_dist_available,
            "ui_dist_available": ui_dist_available,
            "ui_dist_path": str(ui_dist_path),
            "ui_entrypoint": "/" if ui_dist_available else None,
            "ui_mode": ui_mode,
        }

    def _build_server_bind_metadata(self) -> dict:
        host, port = self.server.server_address
        return {
            "host": host,
            "port": port,
            "base_url": f"http://{host}:{port}",
        }

    def _build_release_manifest(self) -> dict:
        return {
            "manifest_version": "phase3-host-baseline",
            "startup_command": (
                "python -m weconduct.cli.main serve-api "
                f"--host {self.server.server_address[0]} "
                f"--port {self.server.server_address[1]} "
                "--workspace-state-path <...> "
                "--preferences-path <...> "
                "--ui-dist-path <...>"
            ),
            "workspace_state_path": "<redacted>",
            "preferences_path": "<redacted>",
            "ui_dist_path": "<redacted>",
        }


def build_api_server(
    *,
    host: str,
    port: int,
    workspace_state_path: str | Path | None = None,
    preferences_path: str | Path | None = None,
    ui_dist_path: str | Path | None = None,
    api_token: str | None = None,
    external_api_enabled: bool | None = None,
    external_api_token: str | None = None,
    external_api_project_allowed_roots: tuple[str | Path, ...] | None = None,
    allow_non_loopback: bool = False,
) -> WeConductApiServer:
    _validate_external_api_bind_host(host, allow_non_loopback=allow_non_loopback)
    server = WeConductApiServer((host, port), WeConductApiHandler)
    server.workspace_state_path = (
        Path(workspace_state_path)
        if workspace_state_path is not None
        else DEFAULT_WORKSPACE_STATE_PATH
    )
    server.preferences_path = (
        Path(preferences_path) if preferences_path is not None else DEFAULT_PREFERENCES_PATH
    )
    server.ui_dist_path = (
        Path(ui_dist_path)
        if ui_dist_path is not None
        else DEFAULT_UI_DIST_PATH
    )
    migration_result = migrate_configuration_storage(server.preferences_path)
    server.configuration_migration_result = migration_result["program"]
    server.graph_configuration_migration_result = migration_result["graph"]
    external_api_configuration = _load_external_api_program_configuration(
        server.preferences_path
    )
    server.api_token = api_token
    server.external_api_enabled = (
        bool(external_api_configuration["enabled"])
        if external_api_enabled is None
        else bool(external_api_enabled)
    )
    server.external_api_token = (
        external_api_configuration["token"]
        if external_api_token is None
        else external_api_token
    )
    configured_roots = external_api_configuration["project_allowed_roots"]
    server.external_api_project_allowed_roots = tuple(
        Path(root).expanduser().resolve()
        for root in (
            configured_roots
            if external_api_project_allowed_roots is None
            else external_api_project_allowed_roots
        )
    )
    return server
