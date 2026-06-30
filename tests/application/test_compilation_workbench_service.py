import json
from pathlib import Path
import subprocess

from weconduct.application import CompilationWorkbenchService
from weconduct.application.preferences_service import PreferencesService
from weconduct.application.preferences_store import InMemoryPreferencesStore
import pytest


def _build_minimal_workspace_graph(*, initial_variables: dict | None = None) -> dict:
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "node-start",
                "lowered_kind": "control",
                "source_anchor_ref": "n-node-start",
                "expansion_role": "flow.start",
                "display_name": "流程入口",
                "node_kind": "flow.start",
                "position": {"x": 0, "y": 0},
                "ports": [
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    }
                ],
                "node_config": {
                    "initial_variables": initial_variables or {"username": "original-user"},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                },
            }
        ],
        "edges": [],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_runtime_sensitive_workspace_graph() -> dict:
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "node-start",
                "lowered_kind": "control",
                "source_anchor_ref": "n-node-start",
                "expansion_role": "flow.start",
                "display_name": "流程入口",
                "node_kind": "flow.start",
                "position": {"x": 0, "y": 0},
                "ports": [
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    }
                ],
                "node_config": {
                    "initial_variables": {"base_url": "https://example.com", "upload_file_path": "input/a.txt"},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                },
            },
            {
                "node_id": "node-browser-goto",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-browser-goto",
                "expansion_role": "browser.goto",
                "display_name": "打开页面",
                "node_kind": "browser.goto",
                "position": {"x": 160, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    },
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    },
                ],
                "node_config": {"url": "${base_url}"},
            },
            {
                "node_id": "node-upload",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-upload",
                "expansion_role": "browser.set_input_files",
                "display_name": "上传文件",
                "node_kind": "browser.set_input_files",
                "position": {"x": 320, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    },
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    },
                ],
                "node_config": {"selector": "#upload", "path": "${upload_file_path}"},
            },
            {
                "node_id": "node-run-python",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-run-python",
                "expansion_role": "python.run",
                "display_name": "运行 Python",
                "node_kind": "python.run",
                "position": {"x": 480, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {"code": "print('hello')"},
            },
        ],
        "edges": [
            {
                "edge_id": "edge-start-goto",
                "from_node_id": "node-start",
                "from_port_id": "control-out",
                "to_node_id": "node-browser-goto",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-goto-upload",
                "from_node_id": "node-browser-goto",
                "from_port_id": "control-out",
                "to_node_id": "node-upload",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-upload-python",
                "from_node_id": "node-upload",
                "from_port_id": "control-out",
                "to_node_id": "node-run-python",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_python_only_workspace_graph() -> dict:
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "node-start",
                "lowered_kind": "control",
                "source_anchor_ref": "n-node-start",
                "expansion_role": "flow.start",
                "display_name": "流程入口",
                "node_kind": "flow.start",
                "position": {"x": 0, "y": 0},
                "ports": [
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    }
                ],
                "node_config": {
                    "initial_variables": {"value": 1},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                },
            },
            {
                "node_id": "node-run-python",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-run-python",
                "expansion_role": "python.run",
                "display_name": "运行 Python",
                "node_kind": "python.run",
                "position": {"x": 160, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {
                    "code": "result = variables.get('value', 0) + 1\nprint(result)\n",
                    "variable_name": "python_result",
                },
            },
        ],
        "edges": [
            {
                "edge_id": "edge-start-python",
                "from_node_id": "node-start",
                "from_port_id": "control-out",
                "to_node_id": "node-run-python",
                "to_port_id": "control-in",
                "relation_layer": "control",
            }
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def test_workbench_service_project_documents_include_custom_node_graph_documents() -> None:
    service = CompilationWorkbenchService()
    graph_payload = {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "node-http",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-http",
                "expansion_role": "action:browser.goto",
                "display_name": "打开页面",
                "node_kind": "browser.goto",
                "position": {"x": 80, "y": 60},
                "ports": [],
            }
        ],
        "edges": [],
        "graph_effective_diagnostic_anchor_refs": [],
    }
    service.save_graph_document(graph_payload)
    save_result = service.save_custom_node_graph_resource(resource_name="登录组件")

    documents = service.get_project_documents_document()
    document_ids = {item["document_id"] for item in documents["documents"]}
    custom_document_id = save_result["resource"]["resource_id"]

    assert documents["main_graph_document_id"] == "graph:workspace"
    assert "graph:workspace" in document_ids
    assert custom_document_id in document_ids
    custom_document = next(
        item for item in documents["documents"] if item["document_id"] == custom_document_id
    )
    assert custom_document["document_role"] == "custom_node_graph"
    assert custom_document["document_type"] == "graph_document"
    assert custom_document["resource_id"] == save_result["resource"]["resource_id"]
    assert custom_document["display_name"] == "登录组件"


def test_workbench_service_can_load_and_save_custom_node_graph_document() -> None:
    service = CompilationWorkbenchService()
    seed_graph_payload = {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
                {
                    "node_id": "node-input",
                    "lowered_kind": "bridge",
                    "source_anchor_ref": "n-input",
                    "expansion_role": "component.input",
                    "display_name": "输入",
                    "node_kind": "component.input",
                    "position": {"x": 40, "y": 40},
                    "ports": [],
                    "node_config": {
                        "name": "name",
                        "value_type": "string",
                        "required": True,
                    },
                }
            ],
        "edges": [],
        "graph_effective_diagnostic_anchor_refs": [],
    }
    service.save_graph_document(seed_graph_payload)
    save_result = service.save_custom_node_graph_resource(resource_name="表单组件")
    resource_id = save_result["resource"]["resource_id"]
    document_id = resource_id

    loaded_document = service.get_graph_document(document_id=document_id)

    assert loaded_document["graph_model"].graph_model_id == document_id
    assert loaded_document["graph_model"].nodes[0].display_name == "输入"

    updated_payload = loaded_document["graph_model"].model_dump(mode="json")
    updated_payload["document_id"] = document_id
    updated_payload["nodes"].append(
        {
            "node_id": "node-output",
            "lowered_kind": "bridge",
            "source_anchor_ref": "n-output",
            "expansion_role": "component.output",
            "display_name": "输出",
            "node_kind": "component.output",
            "position": {"x": 260, "y": 40},
            "ports": [],
            "node_config": {
                "outputs": {
                    "accepted": {
                        "type": "boolean",
                        "required": True,
                    }
                },
            },
        }
    )
    save_document_result = service.save_graph_document(updated_payload)
    resource_registry = service.get_resource_registry_document()
    updated_resource = next(
        item for item in resource_registry["resources"] if item["resource_id"] == resource_id
    )

    assert save_document_result["graph_model"].graph_model_id == document_id
    assert updated_resource["source_graph_document"]["graph_model_id"] == document_id
    assert updated_resource["output_schema"]["accepted"]["type"] == "boolean"


def test_workbench_service_can_create_empty_custom_node_graph_resource() -> None:
    service = CompilationWorkbenchService()

    create_result = service.create_empty_custom_node_graph_resource(resource_name="空白组件")
    resource = create_result["resource"]
    document = service.get_graph_document(document_id=resource["resource_id"])

    assert create_result["status"] == "created"
    assert resource["resource_type"] == "custom_node_graph"
    assert resource["display_name"] == "空白组件"
    assert resource["source_graph_document"]["graph_model_id"] == resource["resource_id"]
    assert document["graph_model"].graph_model_id == resource["resource_id"]
    assert document["graph_model"].nodes == []


def test_workbench_service_returns_compilation_payload() -> None:
    service = CompilationWorkbenchService()

    result = service.compile_source(
        source_kind="native_flow",
        entry_document="examples/service.json",
        source_text='{"nodes":[{"id":"n1","role":"action","capability_domain":"http","action_kind":"request"}]}',
    )

    assert result["outcome"].graph_model is not None
    assert result["outcome"].graph_model.nodes[0].source_anchor_ref == "n1"
    assert result["view"]["graph_stats"]["node_count"] == 1
    assert result["view"]["stage_cards"][-1]["stage"] == "emit"


def test_update_project_runtime_defaults_writes_back_main_flow_start_projection() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph(initial_variables={"username": "before"}))

    update_result = service.update_project_runtime_defaults(
        runtime_defaults={
            "initial_variables": {"username": "after", "token": "abc"},
            "browser_config": {"headless": False},
            "execution_defaults": {
                "default_timeout_ms": 45000,
                "default_retry_count": 2,
            },
        }
    )
    graph_document = service.get_graph_document()
    flow_start = next(node for node in graph_document["graph_model"].nodes if node.node_kind == "flow.start")

    assert update_result["status"] == "updated"
    assert flow_start.node_config["initial_variables"] == {"username": "after", "token": "abc"}
    assert flow_start.node_config["browser_config"] == {"headless": False}
    assert flow_start.node_config["execution_defaults"] == {
        "default_timeout_ms": 45000,
        "default_retry_count": 2,
    }


def test_loaded_wcrun_runtime_blocks_when_manifest_security_requirements_exceed_preferences(
    tmp_path: Path,
) -> None:
    preferences_service = PreferencesService(preferences_store=InMemoryPreferencesStore())
    service = CompilationWorkbenchService(preferences_service=preferences_service)
    graph_payload = _build_runtime_sensitive_workspace_graph()
    service.save_graph_document(graph_payload)
    project_path = tmp_path / "package-security.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings.pop("security_settings", None)
    project_settings["python_runtime_profile"]["runtime_enabled"] = True
    project_settings["resource_policy"]["embedded_resources"] = ["input\\upload-sample.txt"]
    service.update_project_settings(project_settings=project_settings)
    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "package.wcrun",
    )

    loaded_service = CompilationWorkbenchService(preferences_service=preferences_service)
    loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    runtime_result = loaded_service.start_runtime_session(graph_document_payload=None)

    assert runtime_result["status"] == "failed"
    assert runtime_result["runtime_session"]["status"] == "diagnostic_blocked"
    blocked_fields = {entry.get("setting_field") for entry in runtime_result["diagnostics"]["entries"]}
    assert "security_settings.allow_file_access" in blocked_fields
    assert "security_settings.allow_browser_executor" in blocked_fields
    assert "security_settings.allow_python_execution" in blocked_fields
    load_summary = loaded_service.load_project_package(package_path=build_result["package"]["output_path"])[
        "security_requirement_summary"
    ]
    load_blocked_fields = {
        entry.get("setting_field")
        for entry in load_summary.get("blocked_entries", [])
        if isinstance(entry, dict)
    }
    assert load_summary["ready"] is False
    assert "security_settings.allow_file_access" in load_blocked_fields
    assert "security_settings.allow_browser_executor" in load_blocked_fields
    assert "security_settings.allow_python_execution" in load_blocked_fields


def test_build_wcrun_manifest_derives_security_requirements_from_graph_and_project_settings(
    tmp_path: Path,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_runtime_sensitive_workspace_graph())
    project_path = tmp_path / "derived-security.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings.pop("security_settings", None)
    project_settings["python_runtime_profile"]["runtime_enabled"] = True
    project_settings["resource_policy"]["embedded_resources"] = ["input\\upload-sample.txt"]
    service.update_project_settings(project_settings=project_settings)

    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "derived-security.wcrun",
    )
    assert build_result["status"] == "built"
    inspect_result = service.inspect_project_package(package_path=build_result["package"]["output_path"])
    runtime_requirements = inspect_result["package"]["manifest"]["runtime_requirements"]
    security_requirements = runtime_requirements.get("security_requirements")

    assert security_requirements == {
        "allow_file_access": True,
        "allow_browser_executor": True,
        "allow_browser_uploads": True,
        "allow_remote_network_access": True,
        "allow_python_execution": True,
    }


def test_load_wcrun_uses_manifest_security_requirements_when_project_settings_do_not_define_them(
    tmp_path: Path,
) -> None:
    preferences_service = PreferencesService(preferences_store=InMemoryPreferencesStore())
    service = CompilationWorkbenchService(preferences_service=preferences_service)
    service.save_graph_document(_build_runtime_sensitive_workspace_graph())
    project_path = tmp_path / "derived-security-load.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings.pop("security_settings", None)
    project_settings["python_runtime_profile"]["runtime_enabled"] = True
    project_settings["resource_policy"]["embedded_resources"] = ["input\\upload-sample.txt"]
    service.update_project_settings(project_settings=project_settings)

    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "derived-security-load.wcrun",
    )

    loaded_service = CompilationWorkbenchService(preferences_service=preferences_service)
    load_result = loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    summary = load_result["security_requirement_summary"]
    blocked_fields = {
        entry.get("setting_field")
        for entry in summary.get("blocked_entries", [])
        if isinstance(entry, dict)
    }

    assert summary["ready"] is False
    assert "security_settings.allow_file_access" in blocked_fields
    assert "security_settings.allow_browser_executor" in blocked_fields
    assert "security_settings.allow_python_execution" in blocked_fields
    assert summary["required_security_settings"]["allow_browser_uploads"] is True


def test_load_project_package_projects_runtime_defaults_back_into_main_flow_start(
    tmp_path: Path,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph(initial_variables={"username": "before"}))
    project_path = tmp_path / "package-runtime-defaults.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    runtime_defaults = {
        "initial_variables": {"username": "from_settings", "token": "xyz"},
        "browser_config": {"headless": False},
        "execution_defaults": {"default_timeout_ms": 45000, "default_retry_count": 2},
    }
    service.update_project_runtime_defaults(runtime_defaults=runtime_defaults)
    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "package-runtime-defaults.wcrun",
    )

    loaded_service = CompilationWorkbenchService()
    loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    graph_document = loaded_service.get_graph_document()
    flow_start = next(node for node in graph_document["graph_model"].nodes if node.node_kind == "flow.start")

    assert flow_start.node_config["initial_variables"] == runtime_defaults["initial_variables"]
    assert flow_start.node_config["browser_config"] == runtime_defaults["browser_config"]
    assert flow_start.node_config["execution_defaults"] == runtime_defaults["execution_defaults"]


def test_load_project_package_preserves_runtime_default_relative_paths(
    tmp_path: Path,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_runtime_sensitive_workspace_graph()
    )
    project_path = tmp_path / "package-relative-paths.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["resource_policy"]["embedded_resources"] = ["input\\a.txt"]
    service.update_project_settings(project_settings=project_settings)
    (tmp_path / "input").mkdir(parents=True, exist_ok=True)
    (tmp_path / "input" / "a.txt").write_text("payload", encoding="utf-8")

    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "package-relative-paths.wcrun",
    )

    loaded_service = CompilationWorkbenchService()
    load_result = loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    loaded_settings = load_result["project_settings"]
    loaded_initial_variables = loaded_settings["runtime_defaults"]["initial_variables"]

    assert loaded_initial_variables["upload_file_path"] == "input/a.txt"


def test_loaded_wcrun_full_venv_runtime_uses_portable_bundled_python_payload(
    tmp_path: Path,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph(initial_variables={"username": "before"}))
    project_path = tmp_path / "portable-fullvenv.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    python_profile = project_settings["python_runtime_profile"]
    python_profile["runtime_enabled"] = True
    python_profile["project_cache_mode"] = "full_venv"
    python_profile["package_embed_mode"] = "full_venv"
    python_profile["requirements_source_mode"] = "inline"
    python_profile["requirements_inline"] = []
    service.update_project_settings(project_settings=project_settings)
    prepared = service.prepare_project_python_runtime()
    assert prepared["runtime_status"]["health_status"] == "ready"

    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "portable-fullvenv.wcrun",
    )

    loaded_service = CompilationWorkbenchService()
    loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    settings_document = loaded_service.get_project_settings_document()
    runtime_summary = settings_document["python_runtime_summary"]
    session_dir = Path(settings_document["state"]["session_dir"])
    pyvenv_cfg = (
        session_dir
        / "python-runtime"
        / runtime_summary["manifest_hash"]
        / "venv"
        / "pyvenv.cfg"
    ).read_text(encoding="utf-8")
    runtime_root = session_dir / "python-runtime" / runtime_summary["manifest_hash"]
    launch_probe = __import__("subprocess").run(
        [str(runtime_root / "venv" / "Scripts" / "python.exe"), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert runtime_summary["health_status"] == "ready"
    assert f"home = {runtime_root / 'bundled-python'}" in pyvenv_cfg
    assert f"executable = {runtime_root / 'bundled-python' / 'python.exe'}" in pyvenv_cfg
    assert launch_probe.returncode == 0


def test_loaded_wcrun_full_venv_python_run_recovers_from_stale_pyvenv_cfg(
    tmp_path: Path,
) -> None:
    preferences_service = PreferencesService(preferences_store=InMemoryPreferencesStore())
    preferences_service.update_preferences(
        section="security_settings",
        values={
            "allow_python_execution": True,
        },
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(preferences_service=preferences_service)
    service.save_graph_document(_build_python_only_workspace_graph())
    project_path = tmp_path / "portable-fullvenv-pythonrun.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    python_profile = project_settings["python_runtime_profile"]
    python_profile["runtime_enabled"] = True
    python_profile["project_cache_mode"] = "full_venv"
    python_profile["package_embed_mode"] = "full_venv"
    python_profile["requirements_source_mode"] = "inline"
    python_profile["requirements_inline"] = []
    service.update_project_settings(project_settings=project_settings)
    prepared = service.prepare_project_python_runtime()
    assert prepared["runtime_status"]["health_status"] == "ready"

    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "portable-fullvenv-pythonrun.wcrun",
    )

    loaded_service = CompilationWorkbenchService(preferences_service=preferences_service)
    load_result = loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    settings_document = loaded_service.get_project_settings_document()
    runtime_summary = settings_document["python_runtime_summary"]
    session_dir = Path(load_result["project"]["workspace_root"])
    runtime_root = session_dir / "python-runtime" / runtime_summary["manifest_hash"]
    stale_root = Path(r"C:\Users\Administrator\AppData\Local\Temp\2\weconduct-session-stale")
    stale_cfg = (
        f"home = {stale_root / 'bundled-python'}\n"
        "include-system-site-packages = false\n"
        "version = 3.13.5\n"
        f"executable = {stale_root / 'bundled-python' / 'python.exe'}\n"
        f"command = {stale_root / 'bundled-python' / 'python.exe'} -m venv {stale_root / 'venv'}\n"
    )
    (runtime_root / "venv" / "pyvenv.cfg").write_text(stale_cfg, encoding="utf-8")

    session_result = loaded_service.start_runtime_session(graph_document_payload=None)
    assert session_result["status"] == "started"
    run_result = loaded_service.run_runtime_session(
        session_id=session_result["runtime_session"]["session_id"]
    )
    node_states = run_result["node_states"]
    python_node = next(item for item in node_states if item["node_id"] == "node-run-python")

    assert run_result["status"] == "completed", python_node
    assert python_node["node_status"] == "completed", python_node
    assert python_node["output"]["status"] == "succeeded", python_node


def test_loaded_wcrun_full_venv_python_run_recovers_when_runtime_goes_stale_after_session_start(
    tmp_path: Path,
) -> None:
    preferences_service = PreferencesService(preferences_store=InMemoryPreferencesStore())
    preferences_service.update_preferences(
        section="security_settings",
        values={
            "allow_python_execution": True,
        },
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(preferences_service=preferences_service)
    service.save_graph_document(_build_python_only_workspace_graph())
    project_path = tmp_path / "portable-fullvenv-pythonrun-late-stale.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    python_profile = project_settings["python_runtime_profile"]
    python_profile["runtime_enabled"] = True
    python_profile["project_cache_mode"] = "full_venv"
    python_profile["package_embed_mode"] = "full_venv"
    python_profile["requirements_source_mode"] = "inline"
    python_profile["requirements_inline"] = []
    service.update_project_settings(project_settings=project_settings)
    prepared = service.prepare_project_python_runtime()
    assert prepared["runtime_status"]["health_status"] == "ready"

    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "portable-fullvenv-pythonrun-late-stale.wcrun",
    )

    loaded_service = CompilationWorkbenchService(preferences_service=preferences_service)
    load_result = loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    settings_document = loaded_service.get_project_settings_document()
    runtime_summary = settings_document["python_runtime_summary"]
    session_dir = Path(load_result["project"]["workspace_root"])
    runtime_root = session_dir / "python-runtime" / runtime_summary["manifest_hash"]

    session_result = loaded_service.start_runtime_session(graph_document_payload=None)
    assert session_result["status"] == "started"

    stale_root = Path(r"C:\Users\Administrator\AppData\Local\Temp\2\weconduct-session-stale")
    stale_cfg = (
        f"home = {stale_root / 'bundled-python'}\n"
        "include-system-site-packages = false\n"
        "version = 3.13.5\n"
        f"executable = {stale_root / 'bundled-python' / 'python.exe'}\n"
        f"command = {stale_root / 'bundled-python' / 'python.exe'} -m venv {stale_root / 'venv'}\n"
    )
    (runtime_root / "venv" / "pyvenv.cfg").write_text(stale_cfg, encoding="utf-8")

    run_result = loaded_service.run_runtime_session(
        session_id=session_result["runtime_session"]["session_id"]
    )
    node_states = run_result["node_states"]
    python_node = next(item for item in node_states if item["node_id"] == "node-run-python")

    assert run_result["status"] == "completed", python_node
    assert python_node["node_status"] == "completed", python_node
    assert python_node["output"]["status"] == "succeeded", python_node


def test_loaded_wcrun_full_venv_python_run_falls_back_when_launcher_exists_but_is_not_launchable(
    tmp_path: Path,
) -> None:
    preferences_service = PreferencesService(preferences_store=InMemoryPreferencesStore())
    preferences_service.update_preferences(
        section="security_settings",
        values={
            "allow_python_execution": True,
        },
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(preferences_service=preferences_service)
    service.save_graph_document(_build_python_only_workspace_graph())
    project_path = tmp_path / "portable-fullvenv-pythonrun-bad-launcher.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    python_profile = project_settings["python_runtime_profile"]
    python_profile["runtime_enabled"] = True
    python_profile["project_cache_mode"] = "full_venv"
    python_profile["package_embed_mode"] = "full_venv"
    python_profile["requirements_source_mode"] = "inline"
    python_profile["requirements_inline"] = []
    service.update_project_settings(project_settings=project_settings)
    prepared = service.prepare_project_python_runtime()
    assert prepared["runtime_status"]["health_status"] == "ready"

    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "portable-fullvenv-pythonrun-bad-launcher.wcrun",
    )

    loaded_service = CompilationWorkbenchService(preferences_service=preferences_service)
    load_result = loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    settings_document = loaded_service.get_project_settings_document()
    runtime_summary = settings_document["python_runtime_summary"]
    session_dir = Path(load_result["project"]["workspace_root"])
    runtime_root = session_dir / "python-runtime" / runtime_summary["manifest_hash"]
    stale_root = Path(r"C:\Users\Administrator\AppData\Local\Temp\2\weconduct-session-stale")
    stale_cfg = (
        f"home = {stale_root / 'bundled-python'}\n"
        "include-system-site-packages = false\n"
        "version = 3.13.5\n"
        f"executable = {stale_root / 'bundled-python' / 'python.exe'}\n"
        f"command = {stale_root / 'bundled-python' / 'python.exe'} -m venv {stale_root / 'venv'}\n"
    )
    (runtime_root / "venv" / "pyvenv.cfg").write_text(stale_cfg, encoding="utf-8")
    (runtime_root / "venv" / "Scripts" / "python.exe").write_text(
        "broken launcher",
        encoding="utf-8",
    )

    session_result = loaded_service.start_runtime_session(graph_document_payload=None)
    assert session_result["status"] == "started"
    run_result = loaded_service.run_runtime_session(
        session_id=session_result["runtime_session"]["session_id"]
    )
    node_states = run_result["node_states"]
    python_node = next(item for item in node_states if item["node_id"] == "node-run-python")

    assert run_result["status"] == "completed", python_node
    assert python_node["node_status"] == "completed", python_node
    assert python_node["output"]["status"] == "succeeded", python_node


def test_loaded_wcrun_full_venv_python_run_fallback_preserves_third_party_dependencies(
    tmp_path: Path,
) -> None:
    preferences_service = PreferencesService(preferences_store=InMemoryPreferencesStore())
    preferences_service.update_preferences(
        section="security_settings",
        values={
            "allow_python_execution": True,
        },
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(preferences_service=preferences_service)
    service.save_graph_document(_build_python_only_workspace_graph())
    project_path = tmp_path / "portable-fullvenv-pythonrun-reportlab.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    python_profile = project_settings["python_runtime_profile"]
    python_profile["runtime_enabled"] = True
    python_profile["project_cache_mode"] = "full_venv"
    python_profile["package_embed_mode"] = "full_venv"
    python_profile["requirements_source_mode"] = "inline"
    python_profile["requirements_inline"] = ["reportlab==4.2.2"]
    service.update_project_settings(project_settings=project_settings)
    prepared = service.prepare_project_python_runtime()
    assert prepared["runtime_status"]["health_status"] == "ready"

    graph_doc = service.get_graph_document()
    graph_model = graph_doc["graph_model"]
    python_node = next(node for node in graph_model.nodes if node.node_id == "node-run-python")
    python_node.node_config["code"] = (
        "from reportlab.lib import colors\n"
        "result = str(colors.black)\n"
        "print(result)\n"
    )
    service.save_graph_document(graph_model.model_dump(mode="python"))

    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "portable-fullvenv-pythonrun-reportlab.wcrun",
    )

    loaded_service = CompilationWorkbenchService(preferences_service=preferences_service)
    load_result = loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    settings_document = loaded_service.get_project_settings_document()
    runtime_summary = settings_document["python_runtime_summary"]
    session_dir = Path(load_result["project"]["workspace_root"])
    runtime_root = session_dir / "python-runtime" / runtime_summary["manifest_hash"]
    stale_root = Path(r"C:\Users\Administrator\AppData\Local\Temp\2\weconduct-session-stale")
    stale_cfg = (
        f"home = {stale_root / 'bundled-python'}\n"
        "include-system-site-packages = false\n"
        "version = 3.13.5\n"
        f"executable = {stale_root / 'bundled-python' / 'python.exe'}\n"
        f"command = {stale_root / 'bundled-python' / 'python.exe'} -m venv {stale_root / 'venv'}\n"
    )
    (runtime_root / "venv" / "pyvenv.cfg").write_text(stale_cfg, encoding="utf-8")
    (runtime_root / "venv" / "Scripts" / "python.exe").write_text(
        "broken launcher",
        encoding="utf-8",
    )

    session_result = loaded_service.start_runtime_session(graph_document_payload=None)
    assert session_result["status"] == "started"
    run_result = loaded_service.run_runtime_session(
        session_id=session_result["runtime_session"]["session_id"]
    )
    node_states = run_result["node_states"]
    python_node_state = next(item for item in node_states if item["node_id"] == "node-run-python")

    assert run_result["status"] == "completed", python_node_state
    assert python_node_state["node_status"] == "completed", python_node_state
    assert python_node_state["output"]["status"] == "succeeded", python_node_state


def test_loaded_wcrun_full_venv_python_run_reports_process_details_when_child_result_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preferences_service = PreferencesService(preferences_store=InMemoryPreferencesStore())
    preferences_service.update_preferences(
        section="security_settings",
        values={
            "allow_python_execution": True,
        },
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(preferences_service=preferences_service)
    service.save_graph_document(_build_python_only_workspace_graph())
    project_path = tmp_path / "portable-fullvenv-pythonrun-missing-output.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    python_profile = project_settings["python_runtime_profile"]
    python_profile["runtime_enabled"] = True
    python_profile["project_cache_mode"] = "full_venv"
    python_profile["package_embed_mode"] = "full_venv"
    python_profile["requirements_source_mode"] = "inline"
    python_profile["requirements_inline"] = []
    service.update_project_settings(project_settings=project_settings)
    prepared = service.prepare_project_python_runtime()
    assert prepared["runtime_status"]["health_status"] == "ready"

    build_result = service.build_project_package(
        mode="wcrun",
        source_of_truth="saved_project_only",
        output_path=tmp_path / "portable-fullvenv-pythonrun-missing-output.wcrun",
    )

    loaded_service = CompilationWorkbenchService(preferences_service=preferences_service)
    load_result = loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    settings_document = loaded_service.get_project_settings_document()
    runtime_summary = settings_document["python_runtime_summary"]
    session_dir = Path(load_result["project"]["workspace_root"])
    runtime_root = session_dir / "python-runtime" / runtime_summary["manifest_hash"]
    stale_root = Path(r"C:\Users\Administrator\AppData\Local\Temp\2\weconduct-session-stale")
    stale_cfg = (
        f"home = {stale_root / 'bundled-python'}\n"
        "include-system-site-packages = false\n"
        "version = 3.13.5\n"
        f"executable = {stale_root / 'bundled-python' / 'python.exe'}\n"
        f"command = {stale_root / 'bundled-python' / 'python.exe'} -m venv {stale_root / 'venv'}\n"
    )
    (runtime_root / "venv" / "pyvenv.cfg").write_text(stale_cfg, encoding="utf-8")
    (runtime_root / "venv" / "Scripts" / "python.exe").write_text(
        "broken launcher",
        encoding="utf-8",
    )

    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        argv = args[0] if args else kwargs.get("args", [])
        if isinstance(argv, list) and len(argv) >= 2 and str(argv[1]).endswith("runner.py"):
            return subprocess.CompletedProcess(
                args=argv,
                returncode=23,
                stdout="child stdout probe",
                stderr="child stderr probe",
            )
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    session_result = loaded_service.start_runtime_session(graph_document_payload=None)
    assert session_result["status"] == "started"
    run_result = loaded_service.run_runtime_session(
        session_id=session_result["runtime_session"]["session_id"]
    )
    node_states = run_result["node_states"]
    python_node_state = next(item for item in node_states if item["node_id"] == "node-run-python")
    error = python_node_state["error"]
    message = error["message"]

    assert run_result["status"] == "failed", python_node_state
    assert error["error_code"] == "python.execution_failed"
    assert "python.run child result file missing:" in message
    assert "python_executable=" in message
    assert "returncode=23" in message
    assert "stderr=child stderr probe" in message
    assert "stdout=child stdout probe" in message


def test_project_security_settings_report_blocked_entries_and_can_be_enabled(
    tmp_path: Path,
) -> None:
    preferences_service = PreferencesService(preferences_store=InMemoryPreferencesStore())
    service = CompilationWorkbenchService(preferences_service=preferences_service)
    service.save_graph_document(_build_minimal_workspace_graph(initial_variables={"username": "before"}))
    project_path = tmp_path / "package-security.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["security_settings"] = {
        "allow_file_access": True,
        "allow_browser_executor": True,
        "allow_python_execution": True,
    }
    service.update_project_settings(project_settings=project_settings)

    summary_before = service.get_project_settings_document()["security_requirement_summary"]
    enable_result = service.enable_project_required_security_settings(confirm_high_risk=True)
    summary_after = enable_result["security_requirement_summary"]

    assert summary_before["ready"] is False
    assert summary_before["blocked_count"] >= 1
    assert enable_result["status"] == "updated"
    assert summary_after["ready"] is True
    assert summary_after["blocked_count"] == 0
