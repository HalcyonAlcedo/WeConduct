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
    serve_api_parser = subparsers.add_parser("serve-api")
    serve_api_parser.add_argument("--host", default="127.0.0.1")
    serve_api_parser.add_argument("--port", type=int, default=8000)
    serve_api_parser.add_argument("--workspace-state-path", default=None)
    serve_api_parser.add_argument("--preferences-path", default=None)
    serve_api_parser.add_argument("--ui-dist-path", default=None)
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

    args = parser.parse_args()

    if args.command == "compile":
        source_file = Path(args.source_file).resolve()
        service = CompilationWorkbenchService()
        result = service.compile_source(
            source_kind="native_flow",
            entry_document=str(source_file),
            source_text=source_file.read_text(encoding="utf-8"),
        )
        print(json.dumps(result["outcome"].model_dump(), ensure_ascii=False, indent=2))
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
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
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
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
        return 0 if run_result.get("result", {}).get("status") == "succeeded" else 1

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
        print(json.dumps(result, ensure_ascii=False, indent=2))
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

    if args.command is None:
        parser.print_usage()
        return 1

    parser.print_usage()
    return 1


def _json_default(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


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


if __name__ == "__main__":
    raise SystemExit(main())
