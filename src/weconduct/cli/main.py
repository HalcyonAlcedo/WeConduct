import argparse
import json
from pathlib import Path
import sys

from weconduct.application import CompilationWorkbenchService
from weconduct.application.preview_smoke import run_preview_smoke
from weconduct.api import build_api_server
from weconduct.desktop_shell import (
    DesktopShellDependencyError,
    DesktopShellOptions,
    launch_desktop_shell,
    resolve_default_preferences_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="weconduct")
    subparsers = parser.add_subparsers(dest="command")

    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("source_file")
    run_project_parser = subparsers.add_parser("run-project")
    run_project_parser.add_argument("project_file")
    regression_run_parser = subparsers.add_parser("regression-run")
    regression_run_parser.add_argument("project_files", nargs="*")
    regression_run_parser.add_argument("--project-dir", action="append", default=[])
    regression_run_parser.add_argument("--manifest", action="append", default=[])
    regression_run_parser.add_argument("--output", default=None)
    serve_api_parser = subparsers.add_parser("serve-api")
    serve_api_parser.add_argument("--host", default="127.0.0.1")
    serve_api_parser.add_argument("--port", type=int, default=8000)
    serve_api_parser.add_argument("--workspace-state-path", default=None)
    serve_api_parser.add_argument("--preferences-path", default=None)
    serve_api_parser.add_argument("--ui-dist-path", default=None)
    serve_api_parser.add_argument("--api-token", default=None)
    preview_smoke_parser = subparsers.add_parser("preview-smoke")
    preview_smoke_parser.add_argument("--host", default="127.0.0.1")
    preview_smoke_parser.add_argument("--port", type=int, default=0)
    preview_smoke_parser.add_argument("--workspace-state-path", default=None)
    preview_smoke_parser.add_argument("--preferences-path", default=None)
    preview_smoke_parser.add_argument("--ui-dist-path", default=None)
    desktop_shell_parser = subparsers.add_parser("desktop-shell")
    desktop_shell_parser.add_argument("--host", default="127.0.0.1")
    desktop_shell_parser.add_argument("--port", type=int, default=0)
    desktop_shell_parser.add_argument("--workspace-state-path", default=None)
    desktop_shell_parser.add_argument("--preferences-path", default=None)
    desktop_shell_parser.add_argument("--ui-dist-path", default=None)
    desktop_shell_parser.add_argument("--title", default="WeConduct")
    desktop_shell_parser.add_argument("--width", type=int, default=1280)
    desktop_shell_parser.add_argument("--height", type=int, default=800)
    convert_webcontrol_parser = subparsers.add_parser("convert-webcontrol")
    convert_webcontrol_parser.add_argument("source_path")
    convert_webcontrol_parser.add_argument("output_project_path")
    convert_webcontrol_parser.add_argument("--blueprint-path", action="append", default=[])
    convert_webcontrol_parser.add_argument("--blueprint-directory", default=None)
    convert_webcontrol_parser.add_argument("--project-name", default=None)
    convert_webcontrol_parser.add_argument("--overwrite-output", action="store_true")
    convert_webcontrol_parser.add_argument("--auto-open-project", action="store_true")
    convert_webcontrol_parser.add_argument("--no-preserve-legacy-metadata", action="store_true")
    convert_webcontrol_parser.add_argument("--no-write-conversion-report", action="store_true")

    args = parser.parse_args()

    if args.command == "compile":
        source_file = Path(args.source_file).resolve()
        service = CompilationWorkbenchService()
        result = service.compile_source(
            source_kind="native_flow",
            entry_document=str(source_file),
            source_text=source_file.read_text(encoding="utf-8"),
        )
        _print_json(result["outcome"].model_dump())
        return 0

    if args.command == "run-project":
        project_file = Path(args.project_file).resolve()
        service = CompilationWorkbenchService()
        opened = service.open_project(project_path=project_file)
        started = service.start_runtime_session(None)
        if started["status"] != "started":
            payload = {
                "status": "failed",
                "project": opened["project"],
                "project_file": str(project_file),
                "start": started,
            }
            _print_json(payload)
            return 1
        session_id = started["runtime_session"]["session_id"]
        run_result = service.run_runtime_session(session_id=session_id)
        payload = {
            "status": run_result["status"],
            "project": opened["project"],
            "project_file": str(project_file),
            "runtime_session": run_result["runtime_session"],
            "execution_summary": run_result.get("execution_summary"),
            "runtime_preview_summary": service.prepare_runtime_session(None)["runtime_session"]["debug_snapshot"],
            "project_execution_overview": service.get_project_document()["project"]["execution_overview"],
            "runtime_plan": run_result["runtime_plan"],
            "node_states": run_result["node_states"],
            "event_log": run_result["event_log"],
            "result": run_result["result"],
            "regression_summary": _build_runtime_regression_summary(run_result["runtime_plan"]),
        }
        _print_json(payload)
        return 0 if run_result.get("result", {}).get("status") == "succeeded" else 1

    if args.command == "regression-run":
        project_files = _resolve_regression_project_files(
            raw_project_files=args.project_files,
            project_dirs=args.project_dir,
            manifests=args.manifest,
        )
        project_payloads: list[dict] = []
        for project_file in project_files:
            service = CompilationWorkbenchService()
            opened = service.open_project(project_path=project_file)
            started = service.start_runtime_session(None)
            if started["status"] != "started":
                project_payloads.append(
                    {
                        "status": "failed",
                        "project_file": str(project_file),
                        "project": opened["project"],
                        "start": started,
                        "primary_failure_reason": _extract_primary_failure_reason_from_start(started),
                        "failed_node_ids": [],
                        "failed_node_summaries": [],
                        "diagnostic_event_count": len(
                            started.get("diagnostics", {}).get("entries", [])
                            if isinstance(started.get("diagnostics"), dict)
                            else []
                        ),
                        "result_summary": _build_regression_project_result_summary(None),
                    }
                )
                continue
            session_id = started["runtime_session"]["session_id"]
            run_result = service.run_runtime_session(session_id=session_id)
            project_payloads.append(
                {
                    "status": run_result["status"],
                    "project_file": str(project_file),
                    "project": opened["project"],
                    "runtime_session": run_result["runtime_session"],
                    "execution_summary": run_result.get("execution_summary"),
                    "result": run_result.get("result"),
                    "primary_failure_reason": _extract_primary_failure_reason_from_run(run_result),
                    "failed_node_ids": list(run_result.get("result", {}).get("failed_node_ids", []))
                    if isinstance(run_result.get("result"), dict)
                    else [],
                    "failed_node_summaries": _build_failed_node_summaries(run_result),
                    "diagnostic_event_count": len(
                        run_result.get("diagnostic_events", [])
                        if isinstance(run_result.get("diagnostic_events"), list)
                        else []
                    ),
                    "result_summary": _build_regression_project_result_summary(
                        run_result.get("execution_summary")
                    ),
                }
            )
        succeeded_count = len(
            [
                item
                for item in project_payloads
                if item.get("result", {}).get("status") == "succeeded"
            ]
        )
        failed_project_count_by_reason: dict[str, int] = {}
        failed_node_count_by_error_code: dict[str, int] = {}
        failed_node_count_by_kind: dict[str, int] = {}
        failed_projects: list[dict[str, str]] = []
        total_diagnostic_event_count = 0
        for item in project_payloads:
            diagnostic_event_count = item.get("diagnostic_event_count")
            if isinstance(diagnostic_event_count, int):
                total_diagnostic_event_count += diagnostic_event_count
            if item.get("status") != "failed":
                continue
            primary_failure_reason = item.get("primary_failure_reason")
            if isinstance(primary_failure_reason, str) and primary_failure_reason.strip():
                failed_project_count_by_reason[primary_failure_reason] = (
                    failed_project_count_by_reason.get(primary_failure_reason, 0) + 1
                )
            for failed_node_summary in item.get("failed_node_summaries", []):
                if not isinstance(failed_node_summary, dict):
                    continue
                error_code = failed_node_summary.get("error_code")
                if isinstance(error_code, str) and error_code.strip():
                    failed_node_count_by_error_code[error_code] = (
                        failed_node_count_by_error_code.get(error_code, 0) + 1
                    )
                node_kind = failed_node_summary.get("node_kind")
                if isinstance(node_kind, str) and node_kind.strip():
                    failed_node_count_by_kind[node_kind] = (
                        failed_node_count_by_kind.get(node_kind, 0) + 1
                    )
            failed_projects.append(
                {
                    "project_file": item.get("project_file"),
                    "primary_failure_reason": primary_failure_reason,
                }
            )
        payload = {
            "status": "completed",
            "summary": {
                "project_count": len(project_payloads),
                "succeeded_count": succeeded_count,
                "failed_count": len(project_payloads) - succeeded_count,
                "primary_failure_reasons": sorted(
                    {
                        reason
                        for reason in (
                            item.get("primary_failure_reason") for item in project_payloads
                        )
                        if isinstance(reason, str) and reason.strip()
                    }
                ),
                "failed_project_count_by_reason": failed_project_count_by_reason,
                "failed_node_count_by_error_code": failed_node_count_by_error_code,
                "failed_node_count_by_kind": failed_node_count_by_kind,
                "total_diagnostic_event_count": total_diagnostic_event_count,
                "failed_projects": failed_projects,
            },
            "projects": project_payloads,
        }
        _print_json(payload, output_path=args.output)
        return 0 if payload["summary"]["failed_count"] == 0 else 1

    if args.command == "serve-api":
        workspace_state_path = (
            Path(args.workspace_state_path).resolve()
            if args.workspace_state_path is not None
            else None
        )
        preferences_path = (
            Path(args.preferences_path).resolve()
            if args.preferences_path is not None
            else None
        )
        ui_dist_path = (
            Path(args.ui_dist_path).resolve()
            if args.ui_dist_path is not None
            else None
        )
        server = build_api_server(
            host=args.host,
            port=args.port,
            workspace_state_path=workspace_state_path,
            preferences_path=preferences_path,
            ui_dist_path=ui_dist_path,
            api_token=args.api_token,
        )
        runtime_host, runtime_port = server.server_address
        print(
            "WeConduct server listening on "
            f"http://{runtime_host}:{runtime_port} "
            f"(workspace_state_path={server.workspace_state_path}, "
            f"ui_dist_path={server.ui_dist_path})",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0

    if args.command == "preview-smoke":
        workspace_state_path = (
            Path(args.workspace_state_path).resolve()
            if args.workspace_state_path is not None
            else Path(__file__).resolve().parents[3] / ".weconduct" / "preview-smoke-state.json"
        )
        preferences_path = (
            Path(args.preferences_path).resolve()
            if args.preferences_path is not None
            else resolve_default_preferences_path()
        )
        ui_dist_path = (
            Path(args.ui_dist_path).resolve()
            if args.ui_dist_path is not None
            else Path(__file__).resolve().parents[3] / "ui" / "dist"
        )
        result = run_preview_smoke(
            host=args.host,
            port=args.port,
            workspace_state_path=workspace_state_path,
            preferences_path=preferences_path,
            ui_dist_path=ui_dist_path,
        )
        _print_json(result)
        return 0 if result["status"] == "passed" else 1

    if args.command == "desktop-shell":
        workspace_state_path = (
            Path(args.workspace_state_path).resolve()
            if args.workspace_state_path is not None
            else None
        )
        preferences_path = (
            Path(args.preferences_path).resolve()
            if args.preferences_path is not None
            else None
        )
        ui_dist_path = (
            Path(args.ui_dist_path).resolve()
            if args.ui_dist_path is not None
            else None
        )
        try:
            result = launch_desktop_shell(
                DesktopShellOptions(
                    host=args.host,
                    port=args.port,
                    workspace_state_path=workspace_state_path,
                    preferences_path=preferences_path,
                    ui_dist_path=ui_dist_path,
                    title=args.title,
                    width=args.width,
                    height=args.height,
                )
            )
        except DesktopShellDependencyError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        workspace_state_detail = result.get("workspace_state_path", "n/a")
        ui_dist_detail = result.get("ui_dist_path", "n/a")
        print(
            "WeConduct desktop shell closed "
            f"(base_url={result['base_url']}, "
            f"workspace_state_path={workspace_state_detail}, "
            f"ui_dist_path={ui_dist_detail})",
            flush=True,
        )
        return 0

    if args.command == "convert-webcontrol":
        service = CompilationWorkbenchService()
        result = service.convert_webcontrol_project(
            source_path=Path(args.source_path).resolve(),
            blueprint_paths=[Path(item).resolve() for item in args.blueprint_path],
            blueprint_directory=(
                Path(args.blueprint_directory).resolve()
                if args.blueprint_directory is not None
                else None
            ),
            output_project_path=Path(args.output_project_path).resolve(),
            project_name=args.project_name,
            overwrite_output=args.overwrite_output,
            auto_open_project=args.auto_open_project,
            preserve_legacy_metadata=not args.no_preserve_legacy_metadata,
            write_conversion_report=not args.no_write_conversion_report,
        )
        _print_json(result)
        return 0

    if args.command is None:
        parser.print_usage()
        return 1

    parser.print_usage()
    return 1


def _json_default(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


def _serialize_json(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)


def _print_json(payload, *, output_path: str | None = None) -> None:
    text = _serialize_json(payload)
    if output_path is not None:
        Path(output_path).resolve().write_text(text, encoding="utf-8")
    try:
        print(text)
    except UnicodeEncodeError:
        print(json.dumps(payload, ensure_ascii=True, indent=2, default=_json_default))


def _build_runtime_regression_summary(runtime_plan: dict) -> dict:
    executable_nodes = runtime_plan.get("executable_nodes", [])
    domains: set[str] = set()
    for node in executable_nodes:
        if not isinstance(node, dict):
            continue
        node_kind = node.get("node_kind")
        resource_type = node.get("resource_type")
        if resource_type == "custom_node_graph":
            domains.add("graph")
            continue
        if node_kind == "call_blueprint" or resource_type == "user_component":
            domains.add("component")
            continue
        if isinstance(node_kind, str) and node_kind.startswith("control.foreach"):
            domains.add("loop_control")
            continue
        if node_kind == "control.end_foreach":
            domains.add("loop_control")
            continue
        if node_kind == "flow.start":
            continue
        if isinstance(node_kind, str) and "." in node_kind:
            domains.add(node_kind.split(".", 1)[0])
    return {
        "domains": sorted(domains),
        "node_count": runtime_plan.get("node_count", 0),
        "edge_count": runtime_plan.get("edge_count", 0),
    }


def _build_regression_project_result_summary(execution_summary: dict | None) -> dict:
    if not isinstance(execution_summary, dict):
        return {
            "completed_node_count": 0,
            "failed_node_count": 0,
            "event_count": 0,
            "latest_event_kind": None,
        }
    raw_event_count = execution_summary.get("event_count", 0)
    compact_event_count = raw_event_count - 1 if isinstance(raw_event_count, int) and raw_event_count > 0 else 0
    return {
        "completed_node_count": execution_summary.get("completed_node_count", 0),
        "failed_node_count": execution_summary.get("failed_node_count", 0),
        "event_count": compact_event_count,
        "latest_event_kind": execution_summary.get("latest_event_kind"),
    }


def _build_failed_node_summaries(run_result: dict) -> list[dict]:
    node_states = run_result.get("node_states")
    runtime_plan = run_result.get("runtime_plan")
    if not isinstance(node_states, list) or not isinstance(runtime_plan, dict):
        return []
    executable_nodes = runtime_plan.get("executable_nodes")
    if not isinstance(executable_nodes, list):
        return []
    executable_node_map = {
        item.get("node_id"): item for item in executable_nodes if isinstance(item, dict)
    }
    failed_items: list[dict] = []
    for node_state in node_states:
        if not isinstance(node_state, dict):
            continue
        if node_state.get("node_status") != "failed":
            continue
        node_id = node_state.get("node_id")
        executable_node = executable_node_map.get(node_id, {})
        error_payload = node_state.get("error")
        failed_items.append(
            {
                "node_id": node_id,
                "display_name": executable_node.get("display_name"),
                "node_kind": executable_node.get("node_kind"),
                "error_code": (
                    error_payload.get("error_code")
                    if isinstance(error_payload, dict)
                    else None
                ),
                "input_snapshot": node_state.get("input_snapshot"),
            }
        )
    return failed_items


def _resolve_regression_project_files(
    *,
    raw_project_files: list[str],
    project_dirs: list[str],
    manifests: list[str],
) -> list[Path]:
    resolved_files: list[Path] = []
    seen: set[str] = set()

    def add_project_file(project_file: Path) -> None:
        resolved_path = project_file.resolve()
        serialized = str(resolved_path)
        if serialized in seen:
            return
        seen.add(serialized)
        resolved_files.append(resolved_path)

    for raw_project_file in raw_project_files:
        add_project_file(Path(raw_project_file))

    for raw_project_dir in project_dirs:
        project_dir = Path(raw_project_dir).resolve()
        if not project_dir.exists() or not project_dir.is_dir():
            raise ValueError(f"project directory not found: {project_dir}")
        for project_file in sorted(project_dir.rglob("*.weconduct.json")):
            add_project_file(project_file)

    for raw_manifest in manifests:
        manifest_path = Path(raw_manifest).resolve()
        if not manifest_path.exists():
            raise ValueError(f"manifest file not found: {manifest_path}")
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        project_file_items = manifest_payload.get("project_files")
        if not isinstance(project_file_items, list):
            raise ValueError(f"manifest must contain array: project_files ({manifest_path})")
        for item in project_file_items:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"manifest project_files entries must be non-empty strings ({manifest_path})"
                )
            add_project_file(Path(item.strip()))

    if not resolved_files:
        raise ValueError("regression-run requires at least one project file input")
    return resolved_files


def _extract_primary_failure_reason_from_start(start_result: dict) -> str | None:
    diagnostics = start_result.get("diagnostics")
    if isinstance(diagnostics, dict):
        entries = diagnostics.get("entries")
        if isinstance(entries, list) and entries:
            severity_rank = {
                "info": 0,
                "warning": 1,
                "degraded": 2,
                "error": 3,
                "fatal": 4,
            }
            best_entry = None
            best_rank = -1
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                severity = entry.get("severity")
                current_rank = (
                    severity_rank.get(severity.strip(), -1)
                    if isinstance(severity, str)
                    else -1
                )
                if current_rank > best_rank:
                    best_rank = current_rank
                    best_entry = entry
            if isinstance(best_entry, dict):
                category = best_entry.get("category")
                if isinstance(category, str) and category.strip():
                    return category.strip()
    return start_result.get("status") if start_result.get("status") != "started" else None


def _extract_primary_failure_reason_from_run(run_result: dict) -> str | None:
    result = run_result.get("result")
    if isinstance(result, dict):
        failure_reason = result.get("failure_reason")
        if isinstance(failure_reason, str) and failure_reason.strip():
            return failure_reason.strip()
        failed_node_ids = result.get("failed_node_ids")
        if isinstance(failed_node_ids, list) and failed_node_ids:
            return "runtime.node_failed"
    execution_summary = run_result.get("execution_summary")
    if isinstance(execution_summary, dict):
        status = execution_summary.get("status")
        if isinstance(status, str) and status.strip() and status.strip() != "succeeded":
            return status.strip()
    return None


if __name__ == "__main__":
    raise SystemExit(main())
