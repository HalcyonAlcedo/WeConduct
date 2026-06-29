from pathlib import Path

from weconduct.application import CompilationWorkbenchService
from weconduct.application.preferences_service import PreferencesService
from weconduct.application.preferences_store import InMemoryPreferencesStore


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


def test_loaded_wcrun_runtime_blocks_when_project_security_requirements_exceed_preferences(
    tmp_path: Path,
) -> None:
    preferences_service = PreferencesService(preferences_store=InMemoryPreferencesStore())
    service = CompilationWorkbenchService(preferences_service=preferences_service)
    graph_payload = _build_minimal_workspace_graph(initial_variables={"username": "before"})
    service.save_graph_document(graph_payload)
    project_path = tmp_path / "package-security.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["security_settings"] = {
        "allow_file_access": True,
        "allow_browser_executor": True,
        "allow_python_execution": True,
    }
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
