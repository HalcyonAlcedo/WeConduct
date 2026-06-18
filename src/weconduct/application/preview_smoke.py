import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

def run_preview_smoke(
    *,
    host: str,
    port: int,
    workspace_state_path: Path,
    preferences_path: Path | None = None,
    ui_dist_path: Path | None = None,
) -> dict[str, Any]:
    from weconduct.api import build_api_server

    checks: dict[str, dict[str, Any]] = {}
    server = build_api_server(
        host=host,
        port=port,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
    sample_graph = _build_sample_graph_payload()

    try:
        health = _json_request(f"{base_url}/api/health")
        checks["health"] = _build_check(
            ok=health["host_mode"] == "python_core",
            detail=f"host_mode={health['host_mode']}",
        )

        snapshot = _json_request(f"{base_url}/api/workbench/snapshot")
        checks["snapshot"] = _build_check(
            ok=snapshot["entrypoints"]["graph_document"] == "/api/workbench/graph",
            detail=f"snapshot={snapshot['entrypoints']['graph_document']}",
        )

        graph_document = _json_request(f"{base_url}/api/workbench/graph")
        checks["graph_loaded"] = _build_check(
            ok=graph_document["graph_model"]["graph_model_id"] == "graph:workspace",
            detail=f"graph_model_id={graph_document['graph_model']['graph_model_id']}",
        )

        saved_graph = _json_request(
            f"{base_url}/api/workbench/graph",
            method="PUT",
            payload=sample_graph,
        )
        save_revision = saved_graph["view"]["graph_document_save_revision"]
        checks["graph_saved"] = _build_check(
            ok=saved_graph["status"] == "saved"
            and isinstance(save_revision, int)
            and save_revision >= 1,
            detail=(
                "status="
                f"{saved_graph['status']}, revision={save_revision}"
            ),
        )

        validation = _json_request(
            f"{base_url}/api/workbench/graph/validate",
            method="POST",
            payload=sample_graph,
        )
        checks["graph_validated"] = _build_check(
            ok=validation["status"] == "valid" and validation["summary"]["error_count"] == 0,
            detail=(
                "status="
                f"{validation['status']}, errors={validation['summary']['error_count']}"
            ),
        )

        compile_result = _json_request(
            f"{base_url}/api/workbench/graph/compile",
            method="POST",
            payload=sample_graph,
        )
        checks["graph_compiled"] = _build_check(
            ok=compile_result["status"] == "succeeded"
            and compile_result["view"]["graph_stats"]["node_count"] == 2,
            detail=(
                "status="
                f"{compile_result['status']}, nodes={compile_result['view']['graph_stats']['node_count']}"
            ),
        )

        runtime_result = _json_request(
            f"{base_url}/api/workbench/runtime/prepare",
            method="POST",
            payload=sample_graph,
        )
        checks["runtime_prepare"] = _build_check(
            ok=runtime_result["status"] == "ready"
            and runtime_result["runtime_plan"]["node_count"] == 2,
            detail=(
                "status="
                f"{runtime_result['status']}, node_count={runtime_result['runtime_plan']['node_count']}"
            ),
        )

        debug_result = _json_request(
            f"{base_url}/api/workbench/debug/prepare",
            method="POST",
            payload=sample_graph,
        )
        checks["debug_prepare"] = _build_check(
            ok=debug_result["status"] == "ready"
            and len(debug_result["object_index"]["nodes"]) == 2,
            detail=(
                "status="
                f"{debug_result['status']}, nodes={len(debug_result['object_index']['nodes'])}"
            ),
        )

        host_info = _json_request(f"{base_url}/api/host/info")
        checks["host_info"] = _build_check(
            ok=host_info["release_manifest"]["manifest_version"] == "phase3-host-baseline",
            detail=(
                "manifest_version="
                f"{host_info['release_manifest']['manifest_version']}"
            ),
        )

        root_ui = _text_request(f"{base_url}/")
        checks["root_ui_served"] = _build_check(
            ok="<!doctype html>" in root_ui.lower(),
            detail=f"body_prefix={root_ui[:32]}",
        )
    except urllib.error.HTTPError as exc:
        checks.setdefault(
            "root_ui_served",
            _build_check(ok=False, detail=f"HTTP {exc.code}: {exc.reason}"),
        )
    except Exception as exc:  # noqa: BLE001
        checks["unexpected_error"] = _build_check(
            ok=False,
            detail=str(exc),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    failing_checks = [name for name, item in checks.items() if not item["ok"]]
    return {
        "status": "passed" if not failing_checks else "failed",
        "base_url": base_url,
        "workspace_state_path": str(workspace_state_path.resolve()),
        "preferences_path": str(preferences_path.resolve()) if preferences_path is not None else None,
        "ui_dist_path": str(ui_dist_path.resolve()) if ui_dist_path is not None else None,
        "checks": checks,
        "failing_checks": failing_checks,
    }


def _json_request(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if payload is not None or method != "GET" else {},
        method=method,
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _text_request(url: str) -> str:
    with urllib.request.urlopen(url) as response:
        return response.read().decode("utf-8")


def _build_check(*, ok: bool, detail: str) -> dict[str, Any]:
    return {
        "ok": ok,
        "detail": detail,
    }


def _build_sample_graph_payload() -> dict[str, Any]:
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "node-1",
                "lowered_kind": "execution",
                "source_anchor_ref": "n1",
                "expansion_role": "action:request",
                "display_name": "HTTP Request",
                "node_kind": "http.request",
                "position": {"x": 120, "y": 80},
                "ports": [
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "data",
                        "semantic_slot": "out.default",
                    }
                ],
                "node_config": {"method": "GET"},
            },
            {
                "node_id": "node-2",
                "lowered_kind": "execution",
                "source_anchor_ref": "n2",
                "expansion_role": "transform:map",
                "display_name": "Map Result",
                "node_kind": "data.map",
                "position": {"x": 360, "y": 80},
                "ports": [
                    {
                        "port_id": "in",
                        "direction": "input",
                        "relation_layer": "data",
                        "semantic_slot": "in.default",
                    }
                ],
                "node_config": {"mode": "map"},
            },
        ],
        "edges": [
            {
                "edge_id": "edge-1",
                "relation_layer": "data",
                "from_node_id": "node-1",
                "to_node_id": "node-2",
                "from_port_id": "out",
                "to_port_id": "in",
            }
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1.0},
        "graph_effective_diagnostic_anchor_refs": [],
    }
