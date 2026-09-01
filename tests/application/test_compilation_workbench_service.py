import json
from pathlib import Path
from queue import Empty
import subprocess
from threading import Event, Thread
from time import monotonic, sleep

import weconduct.application.compilation_workbench_service as workbench_service_module
from weconduct.application import CompilationWorkbenchService
from weconduct.application.compilation_workbench_service import GraphDocumentRevisionConflictError
from weconduct.application.sensitive_values.encryption import (
    SensitiveUnlockError,
    decrypt_parameter_values,
    encrypt_parameter_values,
)
from weconduct.application.sensitive_values.models import SensitiveRef
from weconduct.application.workspace_state_store import FileWorkspaceStateStore
from weconduct.application.workspace_state_store import InMemoryWorkspaceStateStore
from weconduct.application.configuration import (
    ConfigurationService,
    InMemoryConfigurationRepository,
)
from weconduct.application.configuration.builtin_registry import (
    build_builtin_configuration_registry,
)
from weconduct.application.runtime_projection import project_runtime_value_for_publication
from weconduct.application.workbench_event_stream import WorkbenchEventStreamBroker
from weconduct.contracts import CompilationOutcome, Diagnostic, DiagnosticCatalog, create_initial_summary
from weconduct.network_runtime.resources import ResponseBodyRef
import pytest


@pytest.fixture(autouse=True)
def isolate_application_data_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))


def _build_test_configuration_service() -> ConfigurationService:
    return ConfigurationService(
        registry=build_builtin_configuration_registry(),
        repositories={
            "program": InMemoryConfigurationRepository(),
            "graph": InMemoryConfigurationRepository(),
            "project": InMemoryConfigurationRepository(),
        },
    )


def _update_test_configuration(
    configuration_service: ConfigurationService,
    *,
    section: str,
    values: dict,
    confirm_high_risk: bool = False,
) -> None:
    domain_by_section = {
        "security_settings": "security",
        "python_runtime_settings": "python_defaults",
    }
    domain = domain_by_section[section]
    configuration_service.apply(
        scope="program",
        operations=[
            {"op": "replace", "path": f"/{domain}/{key}", "value": value}
            for key, value in values.items()
        ],
        confirm_high_risk=confirm_high_risk,
    )


class _AliveThread:
    def is_alive(self) -> bool:
        return True

    def join(self, timeout: float | None = None) -> None:
        return None


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


def test_default_graph_workspace_template_uses_http_request_draft_ports() -> None:
    service = CompilationWorkbenchService()

    template = service._build_source_templates()["graph_workspace"]
    graph = json.loads(template["source_text"])
    http_request = graph["nodes"][0]

    assert http_request["node_kind"] == "network.http_request"
    assert {port["port_id"] for port in http_request["ports"]} >= {
        "in:url",
        "out:response",
        "out:network_context_id",
    }
    assert graph["edges"][0]["from_port_id"] == "out:response"


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


def _build_debug_execution_workspace_graph(
    *,
    start_breakpoint_before: bool = False,
    record_frame_on_set_variable: bool = False,
) -> dict:
    start_debugger = (
        {
            "breakpoint": {
                "enabled": True,
                "pause_timing": "before",
            }
        }
        if start_breakpoint_before
        else {}
    )
    set_variable_debugger = (
        {
            "record_frame": {
                "enabled": True,
            }
        }
        if record_frame_on_set_variable
        else {}
    )
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
                    "initial_variables": {"username": "original-user"},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                    "debugger": start_debugger,
                },
            },
            {
                "node_id": "node-set-variable",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-set-variable",
                "expansion_role": "data.set_variable",
                "display_name": "写入变量",
                "node_kind": "data.set_variable",
                "position": {"x": 180, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {
                    "name": "debug_result",
                    "value": "done",
                    "debugger": set_variable_debugger,
                },
            },
        ],
        "edges": [
            {
                "edge_id": "edge-start-set-variable",
                "from_node_id": "node-start",
                "from_port_id": "control-out",
                "to_node_id": "node-set-variable",
                "to_port_id": "control-in",
                "relation_layer": "control",
            }
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_debug_step_workspace_graph() -> dict:
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
                    "initial_variables": {"step_value": "before"},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                    "debugger": {
                        "breakpoint": {
                            "enabled": True,
                            "pause_timing": "before",
                        }
                    },
                },
            },
            {
                "node_id": "node-set-variable",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-set-variable",
                "expansion_role": "data.set_variable",
                "display_name": "写入变量",
                "node_kind": "data.set_variable",
                "position": {"x": 180, "y": 0},
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
                "node_config": {
                    "name": "step_value",
                    "value": "after",
                },
            },
            {
                "node_id": "node-after",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-after",
                "expansion_role": "data.set_variable",
                "display_name": "断点节点",
                "node_kind": "data.set_variable",
                "position": {"x": 360, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {
                    "name": "after_value",
                    "value": "done",
                    "debugger": {
                        "breakpoint": {
                            "enabled": True,
                            "pause_timing": "before",
                        }
                    },
                },
            },
        ],
        "edges": [
            {
                "edge_id": "edge-start-set-variable",
                "from_node_id": "node-start",
                "from_port_id": "control-out",
                "to_node_id": "node-set-variable",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-set-variable-after",
                "from_node_id": "node-set-variable",
                "from_port_id": "control-out",
                "to_node_id": "node-after",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_debug_after_breakpoint_workspace_graph() -> dict:
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
                    "initial_variables": {"after_test_value": "before"},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                    "debugger": {
                        "breakpoint": {
                            "enabled": True,
                            "pause_timing": "before",
                        }
                    },
                },
            },
            {
                "node_id": "node-after-breakpoint",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-after-breakpoint",
                "expansion_role": "data.set_variable",
                "display_name": "执行后断点节点",
                "node_kind": "data.set_variable",
                "position": {"x": 180, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {
                    "name": "after_test_value",
                    "value": "after",
                    "debugger": {
                        "breakpoint": {
                            "enabled": True,
                            "pause_timing": "after",
                        }
                    },
                },
            },
        ],
        "edges": [
            {
                "edge_id": "edge-start-after-breakpoint",
                "from_node_id": "node-start",
                "from_port_id": "control-out",
                "to_node_id": "node-after-breakpoint",
                "to_port_id": "control-in",
                "relation_layer": "control",
            }
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_custom_node_graph_for_debug_step() -> dict:
    return {
        "graph_model_id": "custom_node_graph:debug-step-component",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "component-input",
                "lowered_kind": "control",
                "source_anchor_ref": "n-component-input",
                "expansion_role": "component.input",
                "display_name": "组件输入",
                "node_kind": "component.input",
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
                    "inputs": {
                        "input_value": {
                            "type": "string",
                            "required": False,
                            "default": "from-parent",
                        }
                    }
                },
            },
            {
                "node_id": "component-inner-step",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-component-inner-step",
                "expansion_role": "data.set_variable",
                "display_name": "组件内部节点",
                "node_kind": "data.set_variable",
                "position": {"x": 180, "y": 0},
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
                "node_config": {
                    "name": "component_value",
                    "value": "inside-component",
                    "debugger": {
                        "breakpoint": {
                            "enabled": True,
                            "pause_timing": "before",
                        }
                    },
                },
            },
            {
                "node_id": "component-output",
                "lowered_kind": "control",
                "source_anchor_ref": "n-component-output",
                "expansion_role": "component.output",
                "display_name": "组件输出",
                "node_kind": "component.output",
                "position": {"x": 360, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {
                    "outputs": {
                        "component_value": {
                            "type": "string",
                            "required": False,
                        }
                    }
                },
            },
        ],
        "edges": [
            {
                "edge_id": "edge-component-input-inner",
                "from_node_id": "component-input",
                "from_port_id": "control-out",
                "to_node_id": "component-inner-step",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-component-inner-output",
                "from_node_id": "component-inner-step",
                "from_port_id": "control-out",
                "to_node_id": "component-output",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_custom_node_graph_for_debug_after_step() -> dict:
    payload = _build_custom_node_graph_for_debug_step()
    nodes = payload.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and node.get("node_id") == "component-inner-step":
                node_config = node.get("node_config")
                if not isinstance(node_config, dict):
                    node_config = {}
                debugger = node_config.get("debugger")
                if not isinstance(debugger, dict):
                    debugger = {}
                breakpoint_config = debugger.get("breakpoint")
                if not isinstance(breakpoint_config, dict):
                    breakpoint_config = {}
                breakpoint_config["enabled"] = True
                breakpoint_config["pause_timing"] = "after"
                debugger["breakpoint"] = breakpoint_config
                node_config["debugger"] = debugger
                node["node_config"] = node_config
                break
    return payload


def _build_parent_graph_using_debug_step_component(resource_key: str) -> dict:
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
                    "initial_variables": {"component_value": "outside"},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                    "debugger": {
                        "breakpoint": {
                            "enabled": True,
                            "pause_timing": "before",
                        }
                    },
                },
            },
            {
                "node_id": "node-component-call",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-component-call",
                "expansion_role": "action:custom_node_graph",
                "display_name": "调用子图组件",
                "node_kind": resource_key,
                "position": {"x": 180, "y": 0},
                "ports": [
                    {
                        "port_id": "in.control",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.control",
                    },
                ],
                "node_config": {
                    "inputs": {"input_value": "from-parent"},
                    "outputs": {"component_value": "component_value"},
                },
            },
            {
                "node_id": "node-after-component",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-after-component",
                "expansion_role": "data.set_variable",
                "display_name": "组件后节点",
                "node_kind": "data.set_variable",
                "position": {"x": 360, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {
                    "name": "after_component",
                    "value": "done",
                    "debugger": {
                        "breakpoint": {
                            "enabled": True,
                            "pause_timing": "before",
                        }
                    },
                },
            },
        ],
        "edges": [
            {
                "edge_id": "edge-start-component",
                "from_node_id": "node-start",
                "from_port_id": "control-out",
                "to_node_id": "node-component-call",
                "to_port_id": "in.control",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-component-after",
                "from_node_id": "node-component-call",
                "from_port_id": "out",
                "to_node_id": "node-after-component",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_nested_custom_node_graph_for_debug_step(inner_resource_key: str) -> dict:
    return {
        "graph_model_id": "custom_node_graph:debug-step-nested-component",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "nested-input",
                "lowered_kind": "control",
                "source_anchor_ref": "n-nested-input",
                "expansion_role": "component.input",
                "display_name": "组件输入",
                "node_kind": "component.input",
                "position": {"x": 0, "y": 0},
                "ports": [
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    }
                ],
                "node_config": {"inputs": {}},
            },
            {
                "node_id": "nested-call-inner",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-nested-call-inner",
                "expansion_role": "action:custom_node_graph",
                "display_name": "调用内部子图",
                "node_kind": inner_resource_key,
                "position": {"x": 180, "y": 0},
                "ports": [
                    {
                        "port_id": "in.control",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.control",
                    },
                ],
                "node_config": {
                    "inputs": {"input_value": "from-nested"},
                    "outputs": {"component_value": "component_value"},
                },
            },
            {
                "node_id": "nested-output",
                "lowered_kind": "control",
                "source_anchor_ref": "n-nested-output",
                "expansion_role": "component.output",
                "display_name": "组件输出",
                "node_kind": "component.output",
                "position": {"x": 360, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {
                    "outputs": {
                        "component_value": {
                            "type": "string",
                            "required": False,
                        }
                    }
                },
            },
        ],
        "edges": [
            {
                "edge_id": "edge-nested-input-call",
                "from_node_id": "nested-input",
                "from_port_id": "control-out",
                "to_node_id": "nested-call-inner",
                "to_port_id": "in.control",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-nested-call-output",
                "from_node_id": "nested-call-inner",
                "from_port_id": "out",
                "to_node_id": "nested-output",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_triple_nested_custom_node_graph_for_debug_step(inner_resource_key: str) -> dict:
    return {
        "graph_model_id": "custom_node_graph:debug-step-triple-nested-component",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "triple-input",
                "lowered_kind": "control",
                "source_anchor_ref": "n-triple-input",
                "expansion_role": "component.input",
                "display_name": "组件输入",
                "node_kind": "component.input",
                "position": {"x": 0, "y": 0},
                "ports": [
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    }
                ],
                "node_config": {"inputs": {}},
            },
            {
                "node_id": "triple-call-inner",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-triple-call-inner",
                "expansion_role": "action:custom_node_graph",
                "display_name": "调用内部子图",
                "node_kind": inner_resource_key,
                "position": {"x": 180, "y": 0},
                "ports": [
                    {
                        "port_id": "in.control",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.control",
                    },
                ],
                "node_config": {
                    "inputs": {"input_value": "from-triple"},
                    "outputs": {"component_value": "component_value"},
                },
            },
            {
                "node_id": "triple-output",
                "lowered_kind": "control",
                "source_anchor_ref": "n-triple-output",
                "expansion_role": "component.output",
                "display_name": "组件输出",
                "node_kind": "component.output",
                "position": {"x": 360, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {
                    "outputs": {
                        "component_value": {
                            "type": "string",
                            "required": False,
                        }
                    }
                },
            },
        ],
        "edges": [
            {
                "edge_id": "edge-triple-input-call",
                "from_node_id": "triple-input",
                "from_port_id": "control-out",
                "to_node_id": "triple-call-inner",
                "to_port_id": "in.control",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-triple-call-output",
                "from_node_id": "triple-call-inner",
                "from_port_id": "out",
                "to_node_id": "triple-output",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_parallel_custom_node_graph_for_debug_history(inner_resource_key: str) -> dict:
    return {
        "graph_model_id": "custom_node_graph:debug-parallel-component",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "parallel-input",
                "lowered_kind": "control",
                "source_anchor_ref": "n-parallel-input",
                "expansion_role": "component.input",
                "display_name": "组件输入",
                "node_kind": "component.input",
                "position": {"x": 0, "y": 0},
                "ports": [
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    }
                ],
                "node_config": {"inputs": {}},
            },
            {
                "node_id": "parallel-fork",
                "lowered_kind": "control",
                "source_anchor_ref": "n-parallel-fork",
                "expansion_role": "control:parallel_fork",
                "display_name": "并行分叉",
                "node_kind": "control.parallel_fork",
                "position": {"x": 180, "y": 0},
                "ports": [
                    {
                        "port_id": "in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "branch:left",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.branch:left",
                    },
                    {
                        "port_id": "branch:right",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.branch:right",
                    },
                ],
                "node_config": {
                    "branches": [
                        {"key": "left", "label": "Left"},
                        {"key": "right", "label": "Right"},
                    ]
                },
            },
            {
                "node_id": "parallel-left-call",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-parallel-left-call",
                "expansion_role": "action:custom_node_graph",
                "display_name": "左支调用子图",
                "node_kind": inner_resource_key,
                "position": {"x": 360, "y": -80},
                "ports": [
                    {
                        "port_id": "in.control",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.control",
                    },
                ],
                "node_config": {
                    "inputs": {"input_value": "left"},
                    "outputs": {"component_value": "component_value"},
                },
            },
            {
                "node_id": "parallel-right-call",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-parallel-right-call",
                "expansion_role": "action:custom_node_graph",
                "display_name": "右支调用子图",
                "node_kind": inner_resource_key,
                "position": {"x": 360, "y": 80},
                "ports": [
                    {
                        "port_id": "in.control",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.control",
                    },
                ],
                "node_config": {
                    "inputs": {"input_value": "right"},
                    "outputs": {"component_value": "component_value"},
                },
            },
            {
                "node_id": "parallel-join",
                "lowered_kind": "control",
                "source_anchor_ref": "n-parallel-join",
                "expansion_role": "control:join",
                "display_name": "并行汇合",
                "node_kind": "control.join",
                "position": {"x": 540, "y": 0},
                "ports": [
                    {
                        "port_id": "in:left",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.branch:left",
                    },
                    {
                        "port_id": "in:right",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.branch:right",
                    },
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.control",
                    },
                ],
                "node_config": {
                    "branches": [
                        {"key": "left", "label": "Left"},
                        {"key": "right", "label": "Right"},
                    ],
                    "mode": "all",
                    "quorum": None,
                },
            },
            {
                "node_id": "parallel-output",
                "lowered_kind": "control",
                "source_anchor_ref": "n-parallel-output",
                "expansion_role": "component.output",
                "display_name": "组件输出",
                "node_kind": "component.output",
                "position": {"x": 720, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {
                    "outputs": {
                        "component_value": {
                            "type": "string",
                            "required": False,
                        }
                    }
                },
            },
        ],
        "edges": [
            {
                "edge_id": "edge-parallel-input-fork",
                "from_node_id": "parallel-input",
                "from_port_id": "control-out",
                "to_node_id": "parallel-fork",
                "to_port_id": "in",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-parallel-fork-left",
                "from_node_id": "parallel-fork",
                "from_port_id": "branch:left",
                "to_node_id": "parallel-left-call",
                "to_port_id": "in.control",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-parallel-fork-right",
                "from_node_id": "parallel-fork",
                "from_port_id": "branch:right",
                "to_node_id": "parallel-right-call",
                "to_port_id": "in.control",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-parallel-left-join",
                "from_node_id": "parallel-left-call",
                "from_port_id": "out",
                "to_node_id": "parallel-join",
                "to_port_id": "in:left",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-parallel-right-join",
                "from_node_id": "parallel-right-call",
                "from_port_id": "out",
                "to_node_id": "parallel-join",
                "to_port_id": "in:right",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-parallel-join-output",
                "from_node_id": "parallel-join",
                "from_port_id": "out",
                "to_node_id": "parallel-output",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_debug_while_workspace_graph() -> dict:
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
                    "initial_variables": {"loop_counter": 0},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                    "debugger": {
                        "breakpoint": {
                            "enabled": True,
                            "pause_timing": "before",
                        }
                    },
                },
            },
            {
                "node_id": "node-while",
                "lowered_kind": "control",
                "source_anchor_ref": "n-node-while",
                "expansion_role": "control.while",
                "display_name": "条件循环",
                "node_kind": "control.while",
                "position": {"x": 180, "y": 0},
                "ports": [
                    {
                        "port_id": "in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "repeat",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "repeat",
                    },
                    {
                        "port_id": "loop",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "loop",
                    },
                    {
                        "port_id": "done",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "done",
                    },
                ],
                "node_config": {
                    "expression": "${loop_counter < 2}",
                },
            },
            {
                "node_id": "node-loop-body",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-loop-body",
                "expansion_role": "data.increment_variable",
                "display_name": "循环体节点",
                "node_kind": "data.increment_variable",
                "position": {"x": 360, "y": 0},
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
                "node_config": {
                    "variable_name": "loop_counter",
                    "step": 1,
                    "debugger": {
                        "breakpoint": {
                            "enabled": True,
                            "pause_timing": "before",
                        }
                    },
                },
            },
            {
                "node_id": "node-after-loop",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-after-loop",
                "expansion_role": "data.set_variable",
                "display_name": "循环后节点",
                "node_kind": "data.set_variable",
                "position": {"x": 360, "y": 120},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {
                    "name": "loop_done",
                    "value": "done",
                },
            },
        ],
        "edges": [
            {
                "edge_id": "edge-start-while",
                "from_node_id": "node-start",
                "from_port_id": "control-out",
                "to_node_id": "node-while",
                "to_port_id": "in",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-while-loop-body",
                "from_node_id": "node-while",
                "from_port_id": "loop",
                "to_node_id": "node-loop-body",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-loop-body-while",
                "from_node_id": "node-loop-body",
                "from_port_id": "control-out",
                "to_node_id": "node-while",
                "to_port_id": "repeat",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-while-exit-after-loop",
                "from_node_id": "node-while",
                "from_port_id": "done",
                "to_node_id": "node-after-loop",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_debug_step_workspace_graph_with_condition_expression_breakpoint() -> dict:
    payload = _build_debug_step_workspace_graph()
    nodes = payload.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and node.get("node_id") == "node-after":
                node_config = node.get("node_config")
                if not isinstance(node_config, dict):
                    node_config = {}
                debugger = node_config.get("debugger")
                if not isinstance(debugger, dict):
                    debugger = {}
                breakpoint_config = debugger.get("breakpoint")
                if not isinstance(breakpoint_config, dict):
                    breakpoint_config = {}
                breakpoint_config["enabled"] = True
                breakpoint_config["pause_timing"] = "before"
                breakpoint_config["expression"] = "${step_value == 'after'}"
                debugger["breakpoint"] = breakpoint_config
                node_config["debugger"] = debugger
                node["node_config"] = node_config
                break
    return payload


def _build_debug_step_workspace_graph_with_false_condition_expression_breakpoint() -> dict:
    payload = _build_debug_step_workspace_graph()
    nodes = payload.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and node.get("node_id") == "node-after":
                node_config = node.get("node_config")
                if not isinstance(node_config, dict):
                    node_config = {}
                debugger = node_config.get("debugger")
                if not isinstance(debugger, dict):
                    debugger = {}
                breakpoint_config = debugger.get("breakpoint")
                if not isinstance(breakpoint_config, dict):
                    breakpoint_config = {}
                breakpoint_config["enabled"] = True
                breakpoint_config["pause_timing"] = "before"
                breakpoint_config["expression"] = "${step_value == 'never-hit'}"
                debugger["breakpoint"] = breakpoint_config
                node_config["debugger"] = debugger
                node["node_config"] = node_config
                break
    return payload


def _build_debug_loop_workspace_graph_with_breakpoint_hit_count(hit_count: int) -> dict:
    payload = _build_debug_while_workspace_graph()
    nodes = payload.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and node.get("node_id") == "node-loop-body":
                node_config = node.get("node_config")
                if not isinstance(node_config, dict):
                    node_config = {}
                debugger = node_config.get("debugger")
                if not isinstance(debugger, dict):
                    debugger = {}
                breakpoint_config = debugger.get("breakpoint")
                if not isinstance(breakpoint_config, dict):
                    breakpoint_config = {}
                breakpoint_config["enabled"] = True
                breakpoint_config["pause_timing"] = "before"
                breakpoint_config["hit_count"] = hit_count
                debugger["breakpoint"] = breakpoint_config
                node_config["debugger"] = debugger
                node["node_config"] = node_config
                break
    return payload


def _build_debug_loop_workspace_graph_with_once_breakpoint() -> dict:
    payload = _build_debug_while_workspace_graph()
    nodes = payload.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and node.get("node_id") == "node-loop-body":
                node_config = node.get("node_config")
                if not isinstance(node_config, dict):
                    node_config = {}
                debugger = node_config.get("debugger")
                if not isinstance(debugger, dict):
                    debugger = {}
                breakpoint_config = debugger.get("breakpoint")
                if not isinstance(breakpoint_config, dict):
                    breakpoint_config = {}
                breakpoint_config["enabled"] = True
                breakpoint_config["pause_timing"] = "before"
                breakpoint_config["once"] = True
                debugger["breakpoint"] = breakpoint_config
                node_config["debugger"] = debugger
                node["node_config"] = node_config
                break
    return payload


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
    assert loaded_document["revision"] == 1
    assert loaded_document["view"]["graph_document_save_revision"] == 1

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
    assert save_document_result["view"]["graph_document_save_revision"] == 2
    assert updated_resource["source_graph_document"]["graph_model_id"] == document_id
    assert updated_resource["output_schema"]["accepted"]["type"] == "boolean"


def test_workbench_service_publishes_custom_graph_revision_for_graph_changed_event() -> None:
    broker = WorkbenchEventStreamBroker()
    service = CompilationWorkbenchService(workbench_event_broker=broker)
    subscriber_id, queue = broker.subscribe(snapshot=service.get_workbench_snapshot())

    seed_graph_payload = {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [],
        "edges": [],
        "graph_effective_diagnostic_anchor_refs": [],
    }
    service.save_graph_document(seed_graph_payload)
    queue.get(timeout=0.2)  # workbench.snapshot
    queue.get(timeout=0.2)  # main graph workspace.graph_changed

    resource_id = service.save_custom_node_graph_resource(resource_name="事件组件")["resource"][
        "resource_id"
    ]
    custom_graph = service.get_graph_document(document_id=resource_id)["graph_model"].model_dump(
        mode="json"
    )
    custom_graph["document_id"] = resource_id
    service.save_graph_document(custom_graph)

    event = queue.get(timeout=0.2)
    broker.unsubscribe(subscriber_id)

    assert event["event_name"] == "workspace.graph_changed"
    assert event["payload"] == {
        "document_id": resource_id,
        "revision": 2,
        "reason": "saved",
    }


def test_custom_node_graph_save_rejects_stale_revision_when_required() -> None:
    service = CompilationWorkbenchService()
    seed_graph_payload = {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [],
        "edges": [],
        "graph_effective_diagnostic_anchor_refs": [],
    }
    service.save_graph_document(seed_graph_payload)
    resource_id = service.save_custom_node_graph_resource(resource_name="版本组件")["resource"]["resource_id"]
    document_id = resource_id

    current = service.get_graph_document(document_id=document_id)["graph_model"].model_dump(mode="json")
    service.save_graph_document({**current, "document_id": document_id})
    stale = {**current, "document_id": document_id}

    with pytest.raises(GraphDocumentRevisionConflictError) as error:
        service.save_graph_document(
            stale,
            expected_graph_document_save_revision=0,
            require_expected_revision=True,
        )

    assert error.value.expected_revision == 0
    assert error.value.current_revision == 2
    resource = next(
        item for item in service.get_resource_registry_document()["resources"] if item["resource_id"] == resource_id
    )
    assert resource["source_graph_document_save_revision"] == 2


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


def test_update_graph_entrypoint_runtime_defaults_writes_main_flow_start() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph(initial_variables={"username": "before"}))

    update_result = service.update_graph_entrypoint_runtime_defaults(
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
    project_settings = service.get_project_settings_document()["project_settings"]

    assert update_result["status"] == "updated"
    assert flow_start.node_config["initial_variables"] == {"username": "after", "token": "abc"}
    assert flow_start.node_config["browser_config"] == {"headless": False}
    assert flow_start.node_config["execution_defaults"] == {
        "default_timeout_ms": 45000,
        "default_retry_count": 2,
    }
    assert "runtime_defaults" not in project_settings


def test_workspace_state_migrates_legacy_runtime_defaults_into_flow_start_once() -> None:
    store = InMemoryWorkspaceStateStore()
    seed_service = CompilationWorkbenchService(state_store=store)
    seed_service.save_graph_document(
        _build_minimal_workspace_graph(initial_variables={"username": "graph"})
    )
    legacy_state = store.load()
    assert legacy_state is not None
    legacy_state["project_settings"]["runtime_defaults"] = {
        "initial_variables": {"username": "legacy", "token": "abc"},
        "browser_config": {"headless": False},
        "execution_defaults": {"default_timeout_ms": 45000, "default_retry_count": 2},
    }

    migrated_store = InMemoryWorkspaceStateStore(legacy_state)
    migrated_service = CompilationWorkbenchService(state_store=migrated_store)
    migrated_settings = migrated_service.get_project_settings_document()["project_settings"]
    graph_document = migrated_service.get_graph_document()["graph_model"]
    flow_start = next(node for node in graph_document.nodes if node.node_kind == "flow.start")

    assert "runtime_defaults" not in migrated_settings
    assert flow_start.node_config["initial_variables"] == {
        "username": "legacy",
        "token": "abc",
    }
    assert "runtime_defaults" not in migrated_store.load()["project_settings"]


def test_open_project_persists_legacy_runtime_defaults_migration(tmp_path: Path) -> None:
    project_path = tmp_path / "legacy-runtime.weconduct.json"
    seed_service = CompilationWorkbenchService()
    seed_service.save_graph_document(
        _build_minimal_workspace_graph(initial_variables={"username": "graph"})
    )
    seed_service.save_project_as(project_path=str(project_path))
    storage_root = seed_service._resolve_project_storage_root(project_path)
    settings_path = storage_root / "project-settings.json"
    settings_payload = json.loads(settings_path.read_text(encoding="utf-8"))
    settings_payload["runtime_defaults"] = {
        "initial_variables": {"username": "legacy"},
        "browser_config": {"headless": False},
        "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
    }
    settings_path.write_text(json.dumps(settings_payload), encoding="utf-8")

    loaded_service = CompilationWorkbenchService()
    loaded_service.open_project(project_path=project_path)

    migrated_settings = json.loads(settings_path.read_text(encoding="utf-8"))
    migrated_graph = json.loads((storage_root / "graphs" / "workspace.graph.json").read_text(encoding="utf-8"))
    flow_start = next(node for node in migrated_graph["nodes"] if node["node_kind"] == "flow.start")
    assert "runtime_defaults" not in migrated_settings
    assert flow_start["node_config"]["initial_variables"] == {"username": "legacy"}


def test_runtime_abort_interrupts_active_node_and_is_idempotent(monkeypatch) -> None:
    service = CompilationWorkbenchService()
    node_started = Event()

    def execute_until_cancelled(*, runtime_context, **_kwargs) -> dict:
        node_started.set()
        deadline = monotonic() + 2.0
        while monotonic() < deadline:
            runtime_context.cancellation_context.raise_if_cancelled()
            sleep(0.01)
        raise AssertionError("runtime cancellation was not delivered to the active node")

    monkeypatch.setattr(service, "_execute_runtime_plan_node", execute_until_cancelled)
    started = service.start_runtime_session(
        graph_document_payload=_build_minimal_workspace_graph()
    )
    session_id = started["runtime_session"]["session_id"]

    service.start_runtime_session_execution(session_id=session_id)
    assert node_started.wait(timeout=1.0)

    abort_started_at = monotonic()
    aborted = service.abort_runtime_session(session_id=session_id, reason="user_abort")
    abort_elapsed = monotonic() - abort_started_at

    assert abort_elapsed < 1.0
    assert aborted["status"] == "aborted"
    assert aborted["runtime_session"]["status"] == "aborted"
    assert aborted["runtime_session"]["abort_reason"] == "user_abort"
    assert aborted["runtime_session"]["aborted_at"] is not None
    assert aborted["node_states"][0]["node_status"] == "aborted"
    assert [
        event["event_kind"]
        for event in aborted["event_log"]
        if event["event_kind"] in {"session.aborting", "session.aborted"}
    ] == ["session.aborting", "session.aborted"]

    repeated = service.abort_runtime_session(session_id=session_id, reason="second_abort")
    assert repeated["status"] == "aborted"
    assert repeated["runtime_session"]["abort_reason"] == "user_abort"
    assert sum(
        event["event_kind"] == "session.aborted"
        for event in repeated["event_log"]
    ) == 1


def test_runtime_stream_does_not_publish_running_snapshot_after_abort(monkeypatch) -> None:
    service = CompilationWorkbenchService()
    node_started = Event()
    release_node = Event()
    aborting_published = Event()

    def execute_until_release(*, runtime_context, **_kwargs) -> dict:
        node_started.set()
        while not runtime_context.cancellation_context.is_cancelled:
            sleep(0.005)
        assert release_node.wait(timeout=1.0)
        return {"status": "succeeded", "node_id": "node-start"}

    monkeypatch.setattr(service, "_execute_runtime_plan_node", execute_until_release)
    original_publish_status_snapshot = service._publish_runtime_status_snapshot

    def publish_status_snapshot(*, session_id: str, status: str) -> None:
        original_publish_status_snapshot(session_id=session_id, status=status)
        if status == "aborting":
            aborting_published.set()

    monkeypatch.setattr(service, "_publish_runtime_status_snapshot", publish_status_snapshot)

    started = service.start_runtime_session(
        graph_document_payload=_build_minimal_workspace_graph()
    )
    session_id = started["runtime_session"]["session_id"]
    broker = service._runtime_stream_broker  # type: ignore[attr-defined]
    subscriber_id, queue = broker.subscribe(session_id)
    service.start_runtime_session_execution(session_id=session_id)
    assert node_started.wait(timeout=1.0)

    abort_thread = Thread(
        target=lambda: service.abort_runtime_session(session_id=session_id, reason="user_abort"),
        daemon=True,
    )
    abort_thread.start()
    assert aborting_published.wait(timeout=1.0)
    release_node.set()
    abort_thread.join(timeout=1.0)
    assert not abort_thread.is_alive()
    assert service.get_runtime_session(session_id=session_id)["runtime_session"]["status"] == "aborted"

    events: list[tuple[str, dict]] = []
    deadline = monotonic() + 1.0
    while monotonic() < deadline:
        try:
            item = queue.get(timeout=0.1)
        except Empty:
            break
        if not isinstance(item, tuple):
            break
        event_name, payload = item
        events.append((event_name, payload))

    broker.unsubscribe(session_id, subscriber_id)
    aborting_index = next(
        index
        for index, (event_name, _payload) in enumerate(events)
        if event_name == "runtime.aborting"
    )
    assert all(
        payload.get("status") != "running"
        for event_name, payload in events[aborting_index + 1 :]
        if event_name == "runtime.snapshot"
    )


def test_runtime_abort_forces_terminal_state_when_active_node_ignores_cancellation(monkeypatch) -> None:
    service = CompilationWorkbenchService()
    node_started = Event()
    release_node = Event()

    def execute_without_cancellation_check(**_kwargs) -> dict:
        node_started.set()
        assert release_node.wait(timeout=1.0)
        return {"status": "succeeded", "node_id": "node-start"}

    monkeypatch.setattr(service, "_execute_runtime_plan_node", execute_without_cancellation_check)
    started = service.start_runtime_session(
        graph_document_payload=_build_minimal_workspace_graph()
    )
    session_id = started["runtime_session"]["session_id"]
    service.start_runtime_session_execution(session_id=session_id)
    assert node_started.wait(timeout=1.0)

    release_thread = Thread(target=lambda: (sleep(0.4), release_node.set()), daemon=True)
    release_thread.start()
    abort_started_at = monotonic()
    aborted = service.abort_runtime_session(session_id=session_id, reason="user_abort")
    abort_elapsed = monotonic() - abort_started_at

    assert abort_elapsed < 0.25
    assert aborted["status"] == "aborted"
    assert aborted["runtime_session"]["status"] == "aborted"
    release_thread.join(timeout=1.0)
    worker = service._runtime_execution_threads.get(session_id)  # type: ignore[attr-defined]
    if worker is not None:
        worker.join(timeout=1.0)
    assert service.get_runtime_session(session_id=session_id)["runtime_session"]["status"] == "aborted"


def test_runtime_session_projects_response_refs_before_file_state_persistence(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    state_store = FileWorkspaceStateStore(workspace_state_path)
    CompilationWorkbenchService(state_store=state_store)
    projected = project_runtime_value_for_publication(
        {
            "outputs": {
                "node-response": {
                    "headers": {"Set-Cookie": "session=private-cookie"},
                    "body_ref": ResponseBodyRef(
                        session_id="session-1",
                        storage_kind="memory",
                        size_bytes=4,
                        content_type="application/octet-stream",
                        _payload=b"body",
                    ),
                }
            }
        }
    )
    state_store.mutate(lambda current: {**current, "runtime_output": projected})

    output = state_store.load()["runtime_output"]["outputs"]["node-response"]
    assert output["body_ref"] == {
        "kind": "network_response_body",
        "storage_kind": "memory",
        "size_bytes": 4,
        "content_type": "application/octet-stream",
    }
    assert output["headers"]["Set-Cookie"] == "<redacted>"
    assert "private-cookie" not in workspace_state_path.read_text(encoding="utf-8")


def test_debug_session_projects_response_refs_before_file_state_persistence(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    state_store = FileWorkspaceStateStore(workspace_state_path)
    service = CompilationWorkbenchService(state_store=state_store)
    service.save_graph_document(_build_python_only_workspace_graph())
    project_path = tmp_path / "debug-response-ref.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    session_document = {
        **start_result,
        "variable_snapshot": {
            "response": {
                "body_ref": ResponseBodyRef(
                    session_id=session_id,
                    storage_kind="memory",
                    size_bytes=7,
                    content_type="application/json",
                    _payload=b"private",
                )
            }
        },
    }

    service._replace_debug_session_document(session_document)  # type: ignore[attr-defined]

    persisted_session = next(
        item
        for item in state_store.load()["debug_sessions"]
        if item["debug_session"]["session_id"] == session_id
    )
    assert persisted_session["variable_snapshot"]["response"]["body_ref"] == {
        "kind": "network_response_body",
        "storage_kind": "memory",
        "size_bytes": 7,
        "content_type": "application/json",
    }


def test_debug_worker_completes_when_runtime_values_contain_response_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    state_store = FileWorkspaceStateStore(workspace_state_path)
    service = CompilationWorkbenchService(state_store=state_store)
    service.save_graph_document(_build_python_only_workspace_graph())
    service.save_project_as(project_path=str(tmp_path / "debug-response-worker.weconduct.json"))

    def execute_with_response_ref(
        *, executable_node: dict, runtime_context: object, executor_registry: object
    ) -> dict:
        output: dict = {
            "status": "succeeded",
            "node_id": executable_node["node_id"],
        }
        if executable_node["node_id"] == "node-run-python":
            body_ref = ResponseBodyRef(
                session_id=runtime_context.execution_session_context.session_id,
                storage_kind="memory",
                size_bytes=7,
                content_type="application/json",
                _payload=b"private",
            )
            output["body_ref"] = body_ref
            runtime_context.variables["response"] = {"body_ref": body_ref}
        runtime_context.node_outputs[executable_node["node_id"]] = output
        return output

    monkeypatch.setattr(service, "_execute_runtime_plan_node", execute_with_response_ref)

    result = service.start_debug_session_async(
        graph_document_payload=None,
        settle_timeout_ms=1_000,
    )

    assert result["debug_session"]["status"] == "completed"
    assert result["variable_snapshot"]["response"]["body_ref"] == {
        "kind": "network_response_body",
        "storage_kind": "memory",
        "size_bytes": 7,
        "content_type": "application/json",
    }
    assert not any(
        item.get("category") == "debug.worker_failed"
        for item in result["diagnostic_links"]
    )
    assert "private" not in workspace_state_path.read_text(encoding="utf-8")


def test_workspace_state_keeps_recent_full_runtime_sessions_and_longer_history() -> None:
    service = CompilationWorkbenchService()
    session_ids: list[str] = []

    for _ in range(7):
        started = service.start_runtime_session(
            graph_document_payload=_build_minimal_workspace_graph()
        )
        session_id = started["runtime_session"]["session_id"]
        session_ids.append(session_id)
        service.run_runtime_session(session_id=session_id)

    full_session_ids = [
        item["runtime_session"]["session_id"]
        for item in service._state["runtime_sessions"]  # type: ignore[attr-defined]
    ]
    history_session_ids = [
        item["session_id"]
        for item in service.get_execution_history_document()["runtime_runs"]
    ]

    assert full_session_ids == session_ids[::-1][:5]
    assert history_session_ids == session_ids[::-1]


def test_aborted_runtime_session_cannot_run_again() -> None:
    service = CompilationWorkbenchService()
    started = service.start_runtime_session(
        graph_document_payload=_build_minimal_workspace_graph()
    )
    session_id = started["runtime_session"]["session_id"]

    aborted = service.abort_runtime_session(session_id=session_id, reason="user_abort")

    assert aborted["status"] == "aborted"
    rerun = service.start_runtime_session_execution(session_id=session_id)
    assert rerun["status"] == "aborted"
    assert rerun["runtime_session"]["status"] == "aborted"


def test_project_settings_default_debug_profile_history_retention_limit_is_ten() -> None:
    service = CompilationWorkbenchService()

    project_settings = service.get_project_settings_document()["project_settings"]

    assert project_settings["debug_profile"]["history_retention_limit"] == 10


def test_loaded_wcrun_runtime_blocks_when_manifest_security_requirements_exceed_preferences(
    tmp_path: Path,
) -> None:
    configuration_service = _build_test_configuration_service()
    service = CompilationWorkbenchService(configuration_service=configuration_service)
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

    loaded_service = CompilationWorkbenchService(configuration_service=configuration_service)
    loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    runtime_result = loaded_service.start_runtime_session(graph_document_payload=None)
    debug_prepare_result = loaded_service.prepare_debug_session(graph_document_payload=None)
    debug_start_result = loaded_service.start_debug_session(graph_document_payload=None)

    assert runtime_result["status"] == "failed"
    assert runtime_result["runtime_session"]["status"] == "diagnostic_blocked"
    blocked_fields = {entry.get("setting_field") for entry in runtime_result["diagnostics"]["entries"]}
    assert "security_settings.allow_file_access" in blocked_fields
    assert "security_settings.allow_browser_executor" in blocked_fields
    assert "security_settings.allow_python_execution" in blocked_fields
    assert debug_prepare_result["status"] == "failed"
    assert debug_prepare_result["details"]["primary_diagnostic"]["stage"] == "debug.prepare"
    assert debug_start_result["status"] == "failed"
    assert debug_start_result["details"]["primary_diagnostic"]["category"] == (
        "package.security.requirement_blocked"
    )
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
    configuration_service = _build_test_configuration_service()
    service = CompilationWorkbenchService(configuration_service=configuration_service)
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

    loaded_service = CompilationWorkbenchService(configuration_service=configuration_service)
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
    service.update_graph_entrypoint_runtime_defaults(runtime_defaults=runtime_defaults)
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
    loaded_service.load_project_package(package_path=build_result["package"]["output_path"])
    graph_document = loaded_service.get_graph_document()
    flow_start = next(
        node for node in graph_document["graph_model"].nodes if node.node_kind == "flow.start"
    )
    loaded_initial_variables = flow_start.node_config["initial_variables"]

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
    configuration_service = _build_test_configuration_service()
    _update_test_configuration(
        configuration_service,
        section="security_settings",
        values={
            "allow_python_execution": True,
        },
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(configuration_service=configuration_service)
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

    loaded_service = CompilationWorkbenchService(configuration_service=configuration_service)
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
    configuration_service = _build_test_configuration_service()
    _update_test_configuration(
        configuration_service,
        section="security_settings",
        values={
            "allow_python_execution": True,
        },
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(configuration_service=configuration_service)
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

    loaded_service = CompilationWorkbenchService(configuration_service=configuration_service)
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
    configuration_service = _build_test_configuration_service()
    _update_test_configuration(
        configuration_service,
        section="security_settings",
        values={
            "allow_python_execution": True,
        },
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(configuration_service=configuration_service)
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

    loaded_service = CompilationWorkbenchService(configuration_service=configuration_service)
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
    configuration_service = _build_test_configuration_service()
    _update_test_configuration(
        configuration_service,
        section="security_settings",
        values={
            "allow_python_execution": True,
        },
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(configuration_service=configuration_service)
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

    loaded_service = CompilationWorkbenchService(configuration_service=configuration_service)
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
    configuration_service = _build_test_configuration_service()
    _update_test_configuration(
        configuration_service,
        section="security_settings",
        values={
            "allow_python_execution": True,
        },
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(configuration_service=configuration_service)
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

    loaded_service = CompilationWorkbenchService(configuration_service=configuration_service)
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

    class FakeProcess:
        def __init__(self, args, **kwargs) -> None:
            self.args = args
            self.returncode = 23

        def communicate(self, timeout=None) -> tuple[str, str]:
            return "child stdout probe", "child stderr probe"

        def poll(self) -> int:
            return self.returncode

    real_popen = subprocess.Popen

    def fake_popen(args, **kwargs):
        if isinstance(args, list) and any(str(item).endswith("runner.py") for item in args):
            return FakeProcess(args, **kwargs)
        return real_popen(args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

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
    configuration_service = _build_test_configuration_service()
    service = CompilationWorkbenchService(configuration_service=configuration_service)
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
    snapshot_summary = service.get_workbench_snapshot()["security_requirement_summary"]
    enable_result = service.enable_project_required_security_settings(confirm_high_risk=True)
    summary_after = enable_result["security_requirement_summary"]

    assert summary_before["ready"] is False
    assert snapshot_summary == summary_before
    assert summary_before["blocked_count"] >= 1
    assert enable_result["status"] == "updated"
    assert summary_after["ready"] is True
    assert summary_after["blocked_count"] == 0


def test_project_settings_persist_versioned_encrypted_parameter_set(tmp_path: Path) -> None:
    service = CompilationWorkbenchService()
    project_path = tmp_path / "encrypted-parameters.weconduct.json"
    service.save_project_as(project_path=str(project_path))
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["encrypted_parameter_set"] = {
        "parameter_set_id": "parameters-1",
        "parameters": [{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        "envelope": encrypt_parameter_values(
            {"api_key": "test-secret"},
            password="correct-password",
            parameter_set_id="parameters-1",
        ),
    }

    service.update_project_settings(project_settings=project_settings)

    stored = service.get_project_settings_document()["project_settings"]["encrypted_parameter_set"]
    stored_text = (project_path.parent / "encrypted-parameters.weconduct.data" / "project-settings.json").read_text(
        encoding="utf-8"
    )
    assert stored["parameters"] == [{"parameter_id": "api_key", "name": "API Key", "type": "string"}]
    assert stored["envelope"]["parameter_set_id"] == "parameters-1"
    assert "test-secret" not in stored_text
    assert "correct-password" not in stored_text


def test_project_encrypted_parameter_management_returns_only_summary_and_can_rekey_and_delete() -> None:
    service = CompilationWorkbenchService()

    created = service.configure_project_encrypted_parameters(
        parameter_set_id="parameters-1",
        parameters=[{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        values={"api_key": "test-secret"},
        password="old-password",
        confirm_overwrite=False,
    )
    summary = service.get_project_encrypted_parameter_summary()
    rekeyed = service.rekey_project_encrypted_parameters(
        current_password="old-password",
        new_password="new-password",
    )

    assert created == {
        "configured": True,
        "parameter_set_id": "parameters-1",
        "parameters": [{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
    }
    assert summary == created
    assert rekeyed == created
    assert "test-secret" not in repr(created)
    rekeyed_envelope = service.get_project_settings_document()["project_settings"][
        "encrypted_parameter_set"
    ]["envelope"]
    with pytest.raises(SensitiveUnlockError):
        decrypt_parameter_values(rekeyed_envelope, password="old-password")
    assert decrypt_parameter_values(rekeyed_envelope, password="new-password") == {
        "api_key": "test-secret"
    }
    deleted = service.clear_project_encrypted_parameters(confirm_delete=True)
    assert deleted == {"configured": False, "parameter_set_id": None, "parameters": []}
    assert service.get_project_encrypted_parameter_summary() == deleted


def test_configuring_encrypted_parameters_rejects_initial_variable_name_conflict() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph(initial_variables={"token": "plain"}))

    with pytest.raises(ValueError, match="sensitive_parameter.initial_variable_name_conflict: token"):
        service.configure_project_encrypted_parameters(
            parameter_set_id="parameters-1",
            parameters=[{"parameter_id": "token", "name": "Token", "type": "string"}],
            values={"token": "test-secret"},
            password="correct-password",
            confirm_overwrite=False,
        )


def test_updating_initial_variables_rejects_existing_encrypted_parameter_name_conflict() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    service.configure_project_encrypted_parameters(
        parameter_set_id="parameters-1",
        parameters=[{"parameter_id": "token", "name": "Token", "type": "string"}],
        values={"token": "test-secret"},
        password="correct-password",
        confirm_overwrite=False,
    )

    with pytest.raises(ValueError, match="sensitive_parameter.initial_variable_name_conflict: token"):
        service.update_graph_entrypoint_runtime_defaults(
            runtime_defaults={
                "initial_variables": {"token": "plain"},
                "browser_config": {"headless": True},
                "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
            }
        )


def test_saving_flow_start_initial_variables_rejects_existing_encrypted_parameter_name_conflict() -> None:
    service = CompilationWorkbenchService()
    service.configure_project_encrypted_parameters(
        parameter_set_id="parameters-1",
        parameters=[{"parameter_id": "token", "name": "Token", "type": "string"}],
        values={"token": "test-secret"},
        password="correct-password",
        confirm_overwrite=False,
    )

    with pytest.raises(ValueError, match="sensitive_parameter.initial_variable_name_conflict: token"):
        service.save_graph_document(_build_minimal_workspace_graph(initial_variables={"token": "plain"}))


def test_project_settings_save_rejects_sensitive_initial_variable_name_conflict() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph(initial_variables={"token": "plain"}))
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["encrypted_parameter_set"] = {
        "parameter_set_id": "parameters-1",
        "parameters": [{"parameter_id": "token", "name": "Token", "type": "string"}],
        "envelope": encrypt_parameter_values(
            {"token": "test-secret"},
            password="correct-password",
            parameter_set_id="parameters-1",
        ),
    }
    with pytest.raises(ValueError, match="sensitive_parameter.initial_variable_name_conflict: token"):
        service.update_project_settings(project_settings=project_settings)


def test_runtime_prepare_rejects_persisted_sensitive_initial_variable_name_conflict(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "sensitive-name-conflict.weconduct.json"
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    service.configure_project_encrypted_parameters(
        parameter_set_id="parameters-1",
        parameters=[{"parameter_id": "token", "name": "Token", "type": "string"}],
        values={"token": "test-secret"},
        password="correct-password",
        confirm_overwrite=False,
    )
    service.save_project_as(project_path=project_path)
    graph_path = service._resolve_project_storage_root(project_path) / "graphs" / "workspace.graph.json"
    graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
    graph_payload["nodes"][0]["node_config"]["initial_variables"] = {"token": "plain"}
    graph_path.write_text(json.dumps(graph_payload), encoding="utf-8")

    loaded_service = CompilationWorkbenchService()
    loaded_service.open_project(project_path=project_path)
    result = loaded_service.prepare_runtime_session(None)

    assert result["status"] == "failed"
    assert result["diagnostics"]["entries"][0]["category"] == "runtime.sensitive_variable_name_conflict"
    assert result["diagnostics"]["entries"][0]["setting_field"] == "entrypoint_runtime.initial_variables.token"


def test_debug_prepare_rejects_persisted_sensitive_initial_variable_name_conflict(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "sensitive-debug-name-conflict.weconduct.json"
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    service.configure_project_encrypted_parameters(
        parameter_set_id="parameters-1",
        parameters=[{"parameter_id": "token", "name": "Token", "type": "string"}],
        values={"token": "test-secret"},
        password="correct-password",
        confirm_overwrite=False,
    )
    service.save_project_as(project_path=project_path)
    graph_path = service._resolve_project_storage_root(project_path) / "graphs" / "workspace.graph.json"
    graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
    graph_payload["nodes"][0]["node_config"]["initial_variables"] = {"token": "plain"}
    graph_path.write_text(json.dumps(graph_payload), encoding="utf-8")

    loaded_service = CompilationWorkbenchService()
    loaded_service.open_project(project_path=project_path)
    result = loaded_service.prepare_debug_session(None)

    assert result["status"] == "failed"
    assert result["diagnostic_links"][0]["category"] == "runtime.sensitive_variable_name_conflict"
    assert result["diagnostic_links"][0]["stage"] == "debug.prepare"


def test_runtime_session_unlocks_encrypted_parameter_refs_without_returning_values() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["encrypted_parameter_set"] = {
        "parameter_set_id": "parameters-1",
        "parameters": [{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        "envelope": encrypt_parameter_values(
            {"api_key": "test-secret"},
            password="correct-password",
            parameter_set_id="parameters-1",
        ),
    }
    service.update_project_settings(project_settings=project_settings)
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]

    result = service.unlock_runtime_session_parameters(
        session_id=session_id,
        password="correct-password",
    )

    assert result == {"status": "unlocked", "parameter_ids": ["api_key"]}
    assert "test-secret" not in repr(result)


def test_runtime_session_requires_unlock_before_starting_encrypted_parameters() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["encrypted_parameter_set"] = {
        "parameter_set_id": "parameters-1",
        "parameters": [{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        "envelope": encrypt_parameter_values(
            {"api_key": "test-secret"},
            password="correct-password",
            parameter_set_id="parameters-1",
        ),
    }
    service.update_project_settings(project_settings=project_settings)
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]

    result = service.start_runtime_session_execution(session_id=session_id)

    assert result["status"] == "unlock_required"
    assert result["runtime_session"]["status"] == "unlock_required"
    assert session_id not in service._runtime_execution_threads  # type: ignore[attr-defined]


def test_runtime_session_query_prefers_live_broker_snapshot_for_active_session() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]

    service._runtime_stream_broker.publish_snapshot(  # type: ignore[attr-defined]
        session_id,
        {
            "session_id": session_id,
            "status": "waiting",
            "runtime_session": {
                "session_id": session_id,
                "status": "waiting",
                "completed_node_count": 0,
                "failed_node_count": 0,
            },
            "node_states": [
                {
                    "node_id": "node-start",
                    "node_status": "waiting",
                    "started_at": "2026-08-03T00:00:00Z",
                    "completed_at": None,
                }
            ],
            "event_log": [
                {"event_kind": "runtime.pending_input", "node_id": "node-start"},
                {"event_kind": "runtime.waiting", "node_id": "node-start"},
            ],
            "execution_summary": {
                "status": "waiting",
                "completed_node_count": 0,
                "failed_node_count": 0,
                "event_count": 2,
            },
            "result": None,
        },
    )

    result = service.get_runtime_session(session_id=session_id)

    assert result["runtime_session"]["status"] == "waiting"
    assert result["node_states"] == [
        {
            "node_id": "node-start",
            "node_status": "waiting",
            "started_at": "2026-08-03T00:00:00Z",
            "completed_at": None,
        }
    ]
    assert result["execution_summary"]["status"] == "waiting"
    assert result["execution_summary"]["event_count"] == 2


def test_runtime_session_query_and_sse_snapshot_share_the_same_live_projection() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]

    service._runtime_stream_broker.publish_snapshot(  # type: ignore[attr-defined]
        session_id,
        {
            "session_id": session_id,
            "status": "waiting",
            "runtime_session": {
                "session_id": session_id,
                "status": "waiting",
                "completed_node_count": 1,
                "failed_node_count": 0,
            },
            "node_states": [
                {"node_id": "node-done", "node_status": "completed"},
                {"node_id": "node-waiting", "node_status": "waiting"},
            ],
            "event_log": [
                {"event_kind": "runtime.node", "node_id": "node-done"},
                {"event_kind": "runtime.waiting", "node_id": "node-waiting"},
            ],
            "execution_summary": {"status": "waiting", "event_count": 2},
            "result": None,
        },
    )

    query_projection = service.get_runtime_session(session_id=session_id)
    sse_projection = service.get_runtime_stream_snapshot(session_id=session_id)

    assert sse_projection["runtime_session"] == query_projection["runtime_session"]
    assert sse_projection["node_states"] == query_projection["node_states"]
    assert sse_projection["event_log"] == query_projection["event_log"]
    assert sse_projection["execution_summary"] == query_projection["execution_summary"]


def test_runtime_session_projection_rebuilds_summary_for_visible_transient_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]

    monkeypatch.setattr(
        service,
        "requires_runtime_session_parameter_unlock",
        lambda *, session_id: True,
    )
    service._runtime_stream_broker.publish_snapshot(  # type: ignore[attr-defined]
        session_id,
        {
            "session_id": session_id,
            "status": "running",
            "runtime_session": {
                "session_id": session_id,
                "status": "running",
                "completed_node_count": 1,
                "failed_node_count": 0,
            },
            "node_states": [
                {"node_id": "node-done", "node_status": "completed"},
                {"node_id": "node-running", "node_status": "running"},
                {"node_id": "node-pending", "node_status": "pending"},
            ],
            "event_log": [
                {"event_kind": "runtime.node", "node_id": "node-done"},
                {"event_kind": "diagnostic.raised", "node_id": "node-running"},
                {"event_kind": "runtime.waiting", "node_id": "node-pending"},
            ],
            "execution_summary": {
                "status": "running",
                "completed_node_count": 99,
                "failed_node_count": 7,
                "event_count": 1,
                "diagnostic_event_count": 0,
                "node_status_counts": {"pending": 99},
                "latest_event_kind": "stale",
            },
            "result": {"status": "running"},
        },
    )

    result = service.get_runtime_session(session_id=session_id)

    assert result["runtime_session"]["status"] == "unlock_required"
    assert result["execution_summary"] == {
        "status": "unlock_required",
        "completed_node_count": 1,
        "failed_node_count": 0,
        "event_count": 3,
        "diagnostic_event_count": 1,
        "node_status_counts": {"completed": 1, "running": 1, "pending": 1},
        "latest_event_kind": "runtime.waiting",
    }


def test_runtime_live_status_snapshot_rebuilds_summary_for_sse_consumers() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]

    service._publish_runtime_status_snapshot(  # type: ignore[attr-defined]
        session_id=session_id,
        status="waiting",
    )

    snapshot = service._runtime_stream_broker.get_latest_snapshot(session_id)  # type: ignore[attr-defined]
    assert snapshot is not None
    assert snapshot["status"] == "waiting"
    assert snapshot["runtime_session"]["status"] == "waiting"
    assert snapshot["execution_summary"]["status"] == "waiting"
    assert snapshot["execution_summary"]["event_count"] == len(snapshot["event_log"])


def test_runtime_session_projection_does_not_regress_aborting_to_stale_running_snapshot() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]

    def mark_aborting(state: dict | None) -> dict:
        assert state is not None
        for item in state["runtime_sessions"]:
            if item["runtime_session"]["session_id"] == session_id:
                item["runtime_session"]["status"] = "aborting"
        return state

    service._state_store.mutate(mark_aborting)  # type: ignore[attr-defined]
    service._runtime_stream_broker.publish_snapshot(  # type: ignore[attr-defined]
        session_id,
        {
            "session_id": session_id,
            "status": "running",
            "runtime_session": {"session_id": session_id, "status": "running"},
            "node_states": [{"node_id": "node-start", "node_status": "pending"}],
            "event_log": [],
            "execution_summary": {"status": "running", "event_count": 0},
            "result": None,
        },
    )

    result = service.get_runtime_session(session_id=session_id)

    assert result["runtime_session"]["status"] == "aborting"


def test_runtime_session_projection_prefers_persisted_terminal_state_over_stale_live_snapshot() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]

    def mark_completed(state: dict | None) -> dict:
        assert state is not None
        for item in state["runtime_sessions"]:
            if item["runtime_session"]["session_id"] != session_id:
                continue
            item["runtime_session"].update(
                {
                    "status": "completed",
                    "completed_node_count": 1,
                    "failed_node_count": 0,
                }
            )
            item["node_states"] = [{"node_id": "persisted-node", "node_status": "completed"}]
            item["event_log"] = [{"event_kind": "runtime.completed", "node_id": "persisted-node"}]
            item["execution_summary"] = {
                "status": "succeeded",
                "completed_node_count": 1,
                "failed_node_count": 0,
                "event_count": 1,
            }
            item["result"] = {"status": "succeeded", "source": "persisted"}
            break
        return state

    service._state_store.mutate(mark_completed)  # type: ignore[attr-defined]
    service._runtime_stream_broker.publish_snapshot(  # type: ignore[attr-defined]
        session_id,
        {
            "session_id": session_id,
            "status": "running",
            "runtime_session": {"session_id": session_id, "status": "running"},
            "node_states": [{"node_id": "stale-node", "node_status": "running"}],
            "event_log": [{"event_kind": "runtime.snapshot", "node_id": "stale-node"}],
            "execution_summary": {"status": "running", "event_count": 1},
            "result": {"status": "running", "source": "stale"},
        },
    )

    result = service.get_runtime_session(session_id=session_id)

    assert result["runtime_session"]["status"] == "completed"
    assert result["node_states"][0]["node_id"] == "persisted-node"
    assert result["event_log"] == [{"event_kind": "runtime.completed", "node_id": "persisted-node"}]
    assert result["result"] == {"status": "succeeded", "source": "persisted"}


def test_runtime_session_projection_can_query_while_live_snapshots_publish() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]
    broker = service._runtime_stream_broker  # type: ignore[attr-defined]
    snapshot_published = Event()
    errors: list[BaseException] = []

    def publish_snapshots() -> None:
        try:
            for index in range(100):
                broker.publish_snapshot(
                    session_id,
                    {
                        "session_id": session_id,
                        "status": "running",
                        "runtime_session": {"session_id": session_id, "status": "running"},
                        "node_states": [{"node_id": f"node-{index}", "node_status": "running"}],
                        "event_log": [{"event_kind": "runtime.snapshot", "sequence": index}],
                        "execution_summary": {"status": "running", "event_count": 1},
                        "result": None,
                    },
                )
                snapshot_published.set()
        except BaseException as exc:  # pragma: no cover - assertion is below
            errors.append(exc)

    def query_snapshots() -> None:
        try:
            assert snapshot_published.wait(timeout=1.0)
            for _ in range(100):
                result = service.get_runtime_session(session_id=session_id)
                assert result["runtime_session"]["session_id"] == session_id
                assert result["execution_summary"]["status"] == "running"
        except BaseException as exc:  # pragma: no cover - assertion is below
            errors.append(exc)

    publisher = Thread(target=publish_snapshots, daemon=True)
    querier = Thread(target=query_snapshots, daemon=True)
    publisher.start()
    querier.start()
    publisher.join(timeout=2.0)
    querier.join(timeout=2.0)

    assert not publisher.is_alive()
    assert not querier.is_alive()
    assert errors == []


def test_runtime_session_direct_run_requires_unlock_before_execution() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["encrypted_parameter_set"] = {
        "parameter_set_id": "parameters-1",
        "parameters": [{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        "envelope": encrypt_parameter_values(
            {"api_key": "test-secret"},
            password="correct-password",
            parameter_set_id="parameters-1",
        ),
    }
    service.update_project_settings(project_settings=project_settings)
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]

    result = service.run_runtime_session(session_id=session_id)

    assert result["status"] == "unlock_required"
    assert result["runtime_session"]["status"] == "unlock_required"


def test_project_close_rejects_an_unlocked_waiting_runtime_session() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["encrypted_parameter_set"] = {
        "parameter_set_id": "parameters-close",
        "parameters": [{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        "envelope": encrypt_parameter_values(
            {"api_key": "close-secret"},
            password="close-password",
            parameter_set_id="parameters-close",
        ),
    }
    service.update_project_settings(project_settings=project_settings)
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]

    with pytest.raises(ValueError, match="active_execution"):
        service.close_project(discard_changes=True)

    assert service.get_runtime_session(session_id=session_id)["runtime_session"]["status"] == "unlock_required"


def test_runtime_session_injects_unlocked_parameter_as_sensitive_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["encrypted_parameter_set"] = {
        "parameter_set_id": "parameters-1",
        "parameters": [{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        "envelope": encrypt_parameter_values(
            {"api_key": "test-secret"},
            password="correct-password",
            parameter_set_id="parameters-1",
        ),
    }
    service.update_project_settings(project_settings=project_settings)
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]
    service.unlock_runtime_session_parameters(session_id=session_id, password="correct-password")
    captured_variables: list[dict] = []

    def capture_runtime_context(*, runtime_context, executable_node, **_kwargs) -> dict:
        captured_variables.append(dict(runtime_context.variables))
        return {"status": "succeeded", "node_id": executable_node["node_id"]}

    monkeypatch.setattr(service, "_execute_runtime_plan_node", capture_runtime_context)

    result = service.run_runtime_session(session_id=session_id)

    assert result["status"] == "completed"
    assert captured_variables
    injected_value = captured_variables[0]["api_key"]
    assert isinstance(injected_value, SensitiveRef)
    assert repr(injected_value) == "SensitiveRef(<redacted>)"
    assert "test-secret" not in repr(captured_variables)


def test_debug_session_unlocks_in_memory_parameters_and_reveals_only_while_paused() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    service.configure_project_encrypted_parameters(
        parameter_set_id="parameters-1",
        parameters=[{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        values={"api_key": "debug-secret"},
        password="correct-password",
        confirm_overwrite=False,
    )

    started = service.start_debug_session_async(graph_document_payload=None)

    assert started["status"] == "unlock_required"
    session_id = started["debug_session"]["session_id"]
    assert session_id not in service._debug_execution_threads  # type: ignore[attr-defined]
    assert "debug-secret" not in json.dumps(started)

    service.unlock_debug_session_parameters(
        session_id=session_id,
        password="correct-password",
    )
    deadline = monotonic() + 2.0
    detail = service.get_debug_session(session_id=session_id)
    while detail["debug_session"]["status"] != "paused" and monotonic() < deadline:
        sleep(0.01)
        detail = service.get_debug_session(session_id=session_id)

    assert detail["debug_session"]["status"] == "paused"
    assert detail["variable_snapshot"]["api_key"] in {"<sensitive-ref>", "<redacted>"}
    assert detail["variable_descriptors"]["api_key"]["sensitive"] is True
    assert "debug-secret" not in json.dumps(detail)
    with pytest.raises(SensitiveUnlockError):
        service.reveal_debug_session_sensitive_variables(
            session_id=session_id,
            variable_names=["api_key"],
            password="wrong-password",
        )
    revealed = service.reveal_debug_session_sensitive_variables(
        session_id=session_id,
        variable_names=["api_key"],
        password="correct-password",
    )
    assert revealed["values"] == {"api_key": "debug-secret"}
    history = service.open_debug_history_session(session_id=session_id)
    assert "debug-secret" not in json.dumps(history)
    service.abort_debug_session(
        session_id=session_id,
        reason="test_cleanup",
        settle_timeout_ms=1_000,
    )


def test_debug_execution_keeps_static_configuration_and_variables_out_of_redacted_session_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    graph = _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    graph["nodes"][0]["node_config"]["initial_variables"]["marker"] = "data-test"
    graph["nodes"][1]["node_config"]["value"] = "data-test"
    service.save_graph_document(graph)
    service.configure_project_encrypted_parameters(
        parameter_set_id="parameters-1",
        parameters=[{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        values={"api_key": "test"},
        password="correct-password",
        confirm_overwrite=False,
    )

    captured: list[dict[str, object]] = []

    def capture_execution_inputs(
        *,
        executable_node: dict,
        runtime_context: object,
        executor_registry: object,
    ) -> dict:
        captured.append(
            {
                "node_id": executable_node["node_id"],
                "node_value": executable_node.get("node_config", {}).get("value"),
                "marker": runtime_context.variables.get("marker"),
            }
        )
        return {"status": "succeeded", "node_id": executable_node["node_id"]}

    monkeypatch.setattr(service, "_execute_runtime_plan_node", capture_execution_inputs)
    started = service.start_debug_session_async(graph_document_payload=None)
    session_id = started["debug_session"]["session_id"]
    assert started["status"] == "unlock_required"

    service.unlock_debug_session_parameters(
        session_id=session_id,
        password="correct-password",
    )
    deadline = monotonic() + 2.0
    while service.get_debug_session(session_id=session_id)["debug_session"]["status"] != "paused" and monotonic() < deadline:
        sleep(0.01)

    paused = service.get_debug_session(session_id=session_id)
    assert paused["debug_session"]["status"] == "paused"
    assert "data-test" not in json.dumps(paused)

    service.continue_debug_session_async(session_id=session_id, settle_timeout_ms=1_000)
    deadline = monotonic() + 2.0
    while service.get_debug_session(session_id=session_id)["debug_session"]["status"] != "completed" and monotonic() < deadline:
        sleep(0.01)

    assert service.get_debug_session(session_id=session_id)["debug_session"]["status"] == "completed"
    assert captured == [
        {"node_id": "node-start", "node_value": None, "marker": "data-test"},
        {"node_id": "node-set-variable", "node_value": "data-test", "marker": "data-test"},
    ]


def test_debug_variable_updates_keep_execution_value_in_memory_and_persist_a_redacted_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    graph = _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    graph["nodes"][0]["node_config"]["initial_variables"]["marker"] = "before"
    service.save_graph_document(graph)
    service.configure_project_encrypted_parameters(
        parameter_set_id="parameters-1",
        parameters=[{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        values={"api_key": "test"},
        password="correct-password",
        confirm_overwrite=False,
    )
    captured_markers: list[object] = []

    def capture_execution_inputs(
        *,
        executable_node: dict,
        runtime_context: object,
        executor_registry: object,
    ) -> dict:
        captured_markers.append(runtime_context.variables.get("marker"))
        return {"status": "succeeded", "node_id": executable_node["node_id"]}

    monkeypatch.setattr(service, "_execute_runtime_plan_node", capture_execution_inputs)
    session_id = service.start_debug_session_async(graph_document_payload=None)["debug_session"]["session_id"]
    service.unlock_debug_session_parameters(session_id=session_id, password="correct-password")
    deadline = monotonic() + 2.0
    while service.get_debug_session(session_id=session_id)["debug_session"]["status"] != "paused" and monotonic() < deadline:
        sleep(0.01)

    updated = service.apply_debug_session_variables(
        session_id=session_id,
        updates={"marker": "data-test"},
        apply_mode="immediate",
    )

    assert "data-test" not in json.dumps(updated)
    assert "data-test" not in json.dumps(service.get_debug_session(session_id=session_id))

    service.continue_debug_session_async(session_id=session_id, settle_timeout_ms=1_000)
    deadline = monotonic() + 2.0
    while service.get_debug_session(session_id=session_id)["debug_session"]["status"] != "completed" and monotonic() < deadline:
        sleep(0.01)

    assert captured_markers == ["data-test", "data-test"]


def test_debug_event_append_redacts_resolved_sensitive_values() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    service.configure_project_encrypted_parameters(
        parameter_set_id="parameters-1",
        parameters=[{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        values={"api_key": "debug-secret"},
        password="correct-password",
        confirm_overwrite=False,
    )
    session_id = service.start_debug_session_async(graph_document_payload=None)["debug_session"]["session_id"]
    service.unlock_debug_session_parameters(session_id=session_id, password="correct-password")
    deadline = monotonic() + 2.0
    while service.get_debug_session(session_id=session_id)["debug_session"]["status"] != "paused" and monotonic() < deadline:
        sleep(0.01)

    service._append_debug_session_event(  # type: ignore[attr-defined]
        session_id=session_id,
        event={"event_kind": "debug.test", "payload": {"value": "debug-secret"}},
    )

    detail = service.get_debug_session(session_id=session_id)
    history = service.open_debug_history_session(session_id=session_id)
    assert "debug-secret" not in json.dumps(detail)
    assert "debug-secret" not in json.dumps(history)
    service.abort_debug_session(
        session_id=session_id,
        reason="test_cleanup",
        settle_timeout_ms=1_000,
    )


def test_debug_history_persistence_uses_sensitive_variable_descriptors_without_plaintext_registry(
    tmp_path: Path,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    service.save_project_as(project_path=str(tmp_path / "marked-debug-history.weconduct.json"))
    session_id = "debug-marked-sensitive"

    service._persist_debug_history_session_document(  # type: ignore[attr-defined]
        {
            "debug_session": {
                "session_id": session_id,
                "status": "paused",
                "started_at": "2026-08-08T00:00:00+00:00",
            },
            "object_index": {"graph_model_id": "graph:workspace"},
            "variable_descriptors": {
                "sid": {"name": "sid", "sensitive": True, "value_type": "string"},
            },
            "variable_snapshot": {"sid": "private-session-id"},
            "variable_changes": {"sid": "rotated-session-id"},
            "debug_events": [],
            "debug_keyframes": [],
            "debug_snapshots": [],
        }
    )

    history = service.open_debug_history_session(session_id=session_id)
    persisted_bytes = b"".join(
        path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    )

    assert history["session"]["variable_snapshot"] == {"sid": "<redacted>"}
    assert history["session"]["variable_changes"] == {"sid": "<redacted>"}
    assert b"private-session-id" not in persisted_bytes
    assert b"rotated-session-id" not in persisted_bytes


def test_runtime_sensitive_parameter_rewrite_stays_redacted_and_records_warn_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    service.configure_project_encrypted_parameters(
        parameter_set_id="parameters-1",
        parameters=[{"parameter_id": "token", "name": "Token", "type": "string"}],
        values={"token": "initial-secret"},
        password="correct-password",
        confirm_overwrite=False,
    )
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]
    service.unlock_runtime_session_parameters(session_id=session_id, password="correct-password")

    def rewrite_sensitive_variable(*, runtime_context, executable_node, **_kwargs) -> dict:
        runtime_context.variables["token"] = "rotated-secret"
        return {"status": "succeeded", "node_id": executable_node["node_id"]}

    monkeypatch.setattr(service, "_execute_runtime_plan_node", rewrite_sensitive_variable)
    result = service.run_runtime_session(session_id=session_id)

    audit_events = [
        event
        for event in result["event_log"]
        if event.get("category") == "runtime.sensitive_variable_modified"
    ]
    assert result["status"] == "completed"
    assert result["result"]["variables"]["token"] == "<redacted>"
    assert [
        {
            key: event.get(key)
            for key in (
                "event_kind",
                "category",
                "severity",
                "session_id",
                "node_id",
                "node_kind",
                "variable_name",
                "old_value_type",
                "new_value_type",
            )
        }
        for event in audit_events
    ] == [
        {
            "event_kind": "runtime.sensitive_variable_modified",
            "category": "runtime.sensitive_variable_modified",
            "severity": "warn",
            "session_id": session_id,
            "node_id": "node-start",
            "node_kind": "flow.start",
            "variable_name": "token",
            "old_value_type": "sensitive_ref",
            "new_value_type": "sensitive_ref",
        }
    ]
    assert "initial-secret" not in repr(result)
    assert "rotated-secret" not in repr(result)


def test_runtime_session_redacts_unlocked_parameter_from_persisted_result() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["encrypted_parameter_set"] = {
        "parameter_set_id": "parameters-1",
        "parameters": [{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        "envelope": encrypt_parameter_values(
            {"api_key": "test-secret"},
            password="correct-password",
            parameter_set_id="parameters-1",
        ),
    }
    service.update_project_settings(project_settings=project_settings)
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]
    service.unlock_runtime_session_parameters(session_id=session_id, password="correct-password")

    result = service.run_runtime_session(session_id=session_id)

    assert result["result"]["variables"]["api_key"] == "<redacted>"
    assert "test-secret" not in repr(result)


def test_runtime_session_rejects_parameter_unlock_after_execution_starts() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["encrypted_parameter_set"] = {
        "parameter_set_id": "parameters-1",
        "parameters": [{"parameter_id": "api_key", "name": "API Key", "type": "string"}],
        "envelope": encrypt_parameter_values(
            {"api_key": "test-secret"},
            password="correct-password",
            parameter_set_id="parameters-1",
        ),
    }
    service.update_project_settings(project_settings=project_settings)
    session_id = service.start_runtime_session(graph_document_payload=None)["runtime_session"]["session_id"]
    service._runtime_execution_threads[session_id] = _AliveThread()  # type: ignore[assignment]

    with pytest.raises(ValueError, match="runtime session execution has already started"):
        service.unlock_runtime_session_parameters(
            session_id=session_id,
            password="correct-password",
        )


def test_runtime_session_binds_runtime_context_to_its_session_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    session_id = service.start_runtime_session(
        graph_document_payload=_build_minimal_workspace_graph()
    )["runtime_session"]["session_id"]
    captured_session_ids: list[str] = []

    def capture_runtime_context(*, runtime_context, executable_node, **_kwargs) -> dict:
        captured_session_ids.append(runtime_context.execution_session_context.session_id)
        return {"status": "succeeded", "node_id": executable_node["node_id"]}

    monkeypatch.setattr(service, "_execute_runtime_plan_node", capture_runtime_context)

    result = service.run_runtime_session(session_id=session_id)

    assert result["status"] == "completed"
    assert captured_session_ids == [session_id]


def test_start_debug_session_rejects_when_runtime_session_is_active() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())

    runtime_result = service.start_runtime_session(graph_document_payload=None)

    assert runtime_result["runtime_session"]["status"] == "running"

    debug_result = service.start_debug_session(graph_document_payload=None)

    assert debug_result["status"] == "failed"
    assert "debug_session" not in debug_result
    assert debug_result["diagnostic_links"][0]["category"] == "debug.session_conflict"


def test_start_debug_session_failure_exposes_primary_diagnostic_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())

    summary = create_initial_summary("debug-compile-failed")
    diagnostics = [
        Diagnostic(
            diagnostic_id="debug-compile-failed:parse",
            stage="parse",
            severity="info",
            category="parse.completed",
            message="parsed source document",
        ),
        Diagnostic(
            diagnostic_id="debug-compile-failed:validate",
            stage="validate",
            severity="fatal",
            category="graph.flow_start.invalid_entry_count",
            message="main graph must contain exactly one flow.start node",
        ),
    ]
    outcome = CompilationOutcome(
        graph_model=None,
        compilation_summary=summary,
        diagnostic_catalog=DiagnosticCatalog(entries=diagnostics),
    )
    view = service._build_compile_view(
        status="failed",
        outcome=outcome,
        duration_ms=1,
    )
    fake_compile_result = {
        "status": "failed",
        "request": {
            "compilation_id": "debug-compile-failed",
            "source_kind": "graph_workspace",
            "entry_document": "graph:workspace",
        },
        "outcome": outcome,
        "view": view,
    }

    monkeypatch.setattr(
        service,
        "_compile_graph_document_transient",
        lambda graph_model, compilation_id_prefix="debug": fake_compile_result,
    )

    start_result = service.start_debug_session_async(graph_document_payload=None)

    assert start_result["status"] == "failed"
    assert "debug_session" not in start_result
    assert start_result["diagnostic_links"][0]["category"] == "parse.completed"
    assert start_result["message"] == "main graph must contain exactly one flow.start node"
    assert (
        start_result["details"]["primary_diagnostic"]["category"]
        == "graph.flow_start.invalid_entry_count"
    )


def test_start_debug_session_failure_ignores_parse_completed_as_primary_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())

    summary = create_initial_summary("debug-compile-failed")
    diagnostics = [
        Diagnostic(
            diagnostic_id="debug-compile-failed:parse",
            stage="parse",
            severity="info",
            category="parse.completed",
            message="parsed source document",
        ),
        Diagnostic(
            diagnostic_id="debug-compile-failed:bind",
            stage="bind",
            severity="error",
            category="graph.binding.invalid_reference",
            message="binding failed on node-start",
        ),
    ]
    outcome = CompilationOutcome(
        graph_model=None,
        compilation_summary=summary,
        diagnostic_catalog=DiagnosticCatalog(entries=diagnostics),
    )
    fake_compile_result = {
        "status": "failed",
        "request": {
            "compilation_id": "debug-compile-failed",
            "source_kind": "graph_workspace",
            "entry_document": "graph:workspace",
        },
        "outcome": outcome,
        "view": {
            "primary_diagnostic": {
                "stage": "parse",
                "category": "parse.completed",
                "severity": "info",
                "message": "parsed source document",
            },
            "diagnostic_summary": {
                "total_count": 2,
                "highest_severity": "error",
            },
            "stage_overview": {
                "stages": [],
            },
        },
    }

    monkeypatch.setattr(
        service,
        "_compile_graph_document_transient",
        lambda graph_model, compilation_id_prefix="debug": fake_compile_result,
    )

    start_result = service.start_debug_session_async(graph_document_payload=None)

    assert start_result["status"] == "failed"
    assert start_result["message"] == "binding failed on node-start"
    assert start_result["details"]["primary_diagnostic"]["category"] == "graph.binding.invalid_reference"



def test_start_runtime_session_rejects_when_debug_session_is_active() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))

    debug_result = service.start_debug_session(graph_document_payload=None)

    assert debug_result["debug_session"]["status"] == "paused"

    runtime_result = service.start_runtime_session(graph_document_payload=None)

    assert runtime_result["runtime_session"]["status"] == "diagnostic_blocked"
    assert runtime_result["diagnostics"]["entries"][0]["category"] == "debug.session_conflict"


def test_reloaded_workspace_does_not_treat_stale_paused_debug_session_as_active(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))

    debug_result = service.start_debug_session(graph_document_payload=None)
    assert debug_result["debug_session"]["status"] == "paused"

    reloaded = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    runtime_result = reloaded.start_runtime_session(graph_document_payload=None)

    assert runtime_result["status"] == "started"
    assert runtime_result["runtime_session"]["status"] == "running"


def test_reloaded_workspace_does_not_treat_stale_running_runtime_session_as_active(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_minimal_workspace_graph())

    runtime_result = service.start_runtime_session(graph_document_payload=None)
    assert runtime_result["runtime_session"]["status"] == "running"

    reloaded = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    debug_result = reloaded.start_debug_session(graph_document_payload=None)

    assert debug_result["status"] == "started"
    assert debug_result["debug_session"]["status"] == "completed"


def test_list_debug_sessions_omits_incomplete_unsealed_session() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())

    result = service.start_debug_session(graph_document_payload=None)
    session_id = result["debug_session"]["session_id"]
    service._replace_debug_session_document(  # type: ignore[attr-defined]
        {
            "debug_session": {
                "session_id": session_id,
                "status": "incomplete",
                "started_at": result["debug_session"]["started_at"],
            },
            "request": {},
            "stage_timeline": [],
            "object_index": {"graph_model_id": "graph:workspace"},
            "diagnostic_links": [],
        }
    )

    sessions = service.list_debug_sessions()["sessions"]

    assert sessions == []


def test_start_debug_session_prepares_initial_current_node_projection() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))

    result = service.start_debug_session(graph_document_payload=None)

    assert result["status"] == "started"
    assert result["debug_session"]["status"] == "paused"
    assert result["debug_session"]["paused_reason"] == "breakpoint_hit"
    assert result["runtime_preview"]["current_node"]["node_id"] == "node-start"
    assert result["runtime_preview_summary"]["current_node_id"] == "node-start"


def test_prepare_debug_session_returns_pure_precheck_and_does_not_create_session() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())
    history_before = service.list_debug_history_sessions()["sessions"]

    prepare_result = service.prepare_debug_session(graph_document_payload=None)

    assert prepare_result["status"] == "ready"
    assert "debug_session" not in prepare_result
    assert service.list_debug_sessions()["sessions"] == []
    assert service.list_debug_history_sessions()["sessions"] == history_before

    start_result = service.start_debug_session(graph_document_payload=None)

    assert start_result["status"] == "started"
    assert start_result["debug_session"]["status"] == "completed"


def test_prepare_runtime_session_returns_pure_precheck_and_does_not_create_session() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())

    prepare_result = service.prepare_runtime_session(graph_document_payload=None)

    assert prepare_result["status"] == "ready"
    assert "runtime_session" not in prepare_result
    assert service.list_runtime_sessions()["sessions"] == []
    assert service._prepare_runtime_execution(None).security_requirement_summary is not None


def test_prepare_runtime_session_rejects_when_debug_session_is_active() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))

    debug_result = service.start_debug_session(graph_document_payload=None)
    assert debug_result["debug_session"]["status"] == "paused"

    prepare_result = service.prepare_runtime_session(graph_document_payload=None)

    assert prepare_result["status"] == "failed"
    assert prepare_result["diagnostics"]["entries"][0]["category"] == "debug.session_conflict"
    assert prepare_result["diagnostics"]["entries"][0]["stage"] == "runtime.prepare"


def test_prepare_debug_session_rejects_when_runtime_session_is_active() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))

    runtime_result = service.start_runtime_session(graph_document_payload=None)
    assert runtime_result["runtime_session"]["status"] == "running"

    prepare_result = service.prepare_debug_session(graph_document_payload=None)

    assert prepare_result["status"] == "failed"
    assert prepare_result["details"]["primary_diagnostic"]["category"] == "debug.session_conflict"
    assert prepare_result["stage_timeline"] == []


def test_continue_debug_session_runs_until_breakpoint_and_pauses() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    assert start_result["debug_session"]["session_id"] == session_id
    assert start_result["debug_session"]["status"] == "paused"
    assert start_result["debug_session"]["paused_reason"] == "breakpoint_hit"
    assert start_result["runtime_preview"]["current_node"]["node_id"] == "node-start"

    events_payload = service.list_debug_session_events(session_id=session_id)
    assert events_payload["events"][-2]["event_kind"] == "breakpoint.hit"
    assert events_payload["events"][-1]["event_kind"] == "debug.paused"


def test_continue_debug_session_runs_to_completion_without_breakpoint() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(record_frame_on_set_variable=True)
    )

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    assert start_result["debug_session"]["session_id"] == session_id
    assert start_result["debug_session"]["status"] == "completed"
    assert start_result["runtime_preview"]["executed_node_ids"] == [
        "node-start",
        "node-set-variable",
    ]
    assert start_result["variable_snapshot"]["debug_result"] == "done"

    events_payload = service.list_debug_session_events(session_id=session_id)
    assert any(item["event_kind"] == "record_frame.hit" for item in events_payload["events"])


def test_paused_debug_session_hits_breakpoint_added_after_start() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    started = service.start_debug_session(graph_document_payload=None)
    session_id = started["debug_session"]["session_id"]

    updated = service.update_debug_session_node_debugger(
        session_id=session_id,
        node_id="node-set-variable",
        debugger_config={
            "breakpoint": {
                "enabled": True,
                "pause_timing": "before",
                "hit_count": 0,
                "once": False,
            },
            "record_frame": {"enabled": False},
        },
    )
    continued = service.continue_debug_session(session_id=session_id)

    assert updated["status"] == "updated"
    assert continued["debug_session"]["status"] == "paused"
    assert continued["debug_session"]["paused_reason"] == "breakpoint_hit"
    assert continued["runtime_preview"]["current_node"]["node_id"] == "node-set-variable"


def test_async_paused_debug_session_hits_breakpoint_added_after_start() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    started = service.start_debug_session_async(graph_document_payload=None)
    session_id = started["debug_session"]["session_id"]

    try:
        service.update_debug_session_node_debugger(
            session_id=session_id,
            node_id="node-set-variable",
            debugger_config={
                "breakpoint": {
                    "enabled": True,
                    "pause_timing": "before",
                    "hit_count": 0,
                    "once": False,
                },
                "record_frame": {"enabled": False},
            },
        )
        continued = service.continue_debug_session_async(
            session_id=session_id,
            settle_timeout_ms=500,
        )

        assert continued["debug_session"]["status"] == "paused"
        assert continued["debug_session"]["paused_reason"] == "breakpoint_hit"
        assert continued["runtime_preview"]["current_node"]["node_id"] == "node-set-variable"
    finally:
        worker = service._debug_execution_threads.get(session_id)  # type: ignore[attr-defined]
        if worker is not None and worker.is_alive():
            service.abort_debug_session(
                session_id=session_id,
                reason="test_cleanup",
                settle_timeout_ms=500,
            )


def test_paused_debug_session_records_frame_added_after_start(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    service.save_project_as(project_path=str(tmp_path / "debug-hot-record-frame.weconduct.json"))
    started = service.start_debug_session(graph_document_payload=None)
    session_id = started["debug_session"]["session_id"]

    service.update_debug_session_node_debugger(
        session_id=session_id,
        node_id="node-set-variable",
        debugger_config={
            "breakpoint": {"enabled": False, "pause_timing": "before"},
            "record_frame": {"enabled": True},
        },
    )
    completed = service.continue_debug_session(session_id=session_id)
    history = service.open_debug_history_session(session_id=session_id)["session"]

    assert completed["debug_session"]["status"] == "completed"
    assert any(
        item.get("event_kind") == "record_frame.hit"
        and item.get("node_id") == "node-set-variable"
        for item in history["snapshots"]
    )


def test_start_runtime_session_allows_after_async_debug_completion() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))

    start_result = service.start_debug_session_async(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    assert start_result["debug_session"]["status"] == "paused"

    # Generous settle window: _await_debug_execution_settle returns as soon as
    # the session reaches a terminal status, so this adds no latency to the
    # normal case but removes flakiness when the worker is CPU-starved under
    # full-suite parallel load.
    continue_result = service.continue_debug_session_async(
        session_id=session_id,
        settle_timeout_ms=5000,
    )

    assert continue_result["debug_session"]["status"] == "completed"
    assert service.list_debug_sessions()["sessions"] == []

    runtime_result = service.start_runtime_session(graph_document_payload=None)

    assert runtime_result["runtime_session"]["status"] == "running"


def test_shutdown_debug_sessions_aborts_paused_worker_and_releases_runtime_context() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    start_result = service.start_debug_session_async(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    worker = service._debug_execution_threads[session_id]  # type: ignore[attr-defined]

    try:
        service.shutdown_debug_sessions(reason="application_shutdown", timeout_seconds=1.0)

        assert worker.is_alive() is False
        assert service.get_debug_session(session_id=session_id)["debug_session"]["status"] == "aborted"
        assert session_id not in service._debug_execution_threads  # type: ignore[attr-defined]
        assert session_id not in service._debug_runtime_contexts  # type: ignore[attr-defined]
    finally:
        if worker.is_alive():
            service.abort_debug_session(
                session_id=session_id,
                reason="test_cleanup",
                settle_timeout_ms=500,
            )


def test_launch_debug_execution_thread_cleans_registries_when_thread_start_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    session_id = "debug-session-start-failure"

    class StartFailingThread:
        def __init__(self, **_: object) -> None:
            pass

        def is_alive(self) -> bool:
            return False

        def start(self) -> None:
            raise RuntimeError("thread start failed")

    monkeypatch.setattr(workbench_service_module, "Thread", StartFailingThread)

    launched = service._launch_debug_execution_thread(session_id=session_id)  # type: ignore[attr-defined]

    assert launched is False
    assert session_id not in service._debug_execution_threads  # type: ignore[attr-defined]
    assert session_id not in service._debug_execution_resume_events  # type: ignore[attr-defined]


def test_debug_worker_failure_marks_session_failed_and_releases_runtime_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    original_persist = service._persist_debug_history_session_document  # type: ignore[attr-defined]
    persist_call_count = 0

    def fail_worker_history_persist(session_document: dict) -> None:
        nonlocal persist_call_count
        persist_call_count += 1
        if persist_call_count >= 2:
            raise OSError("history storage unavailable")
        original_persist(session_document)

    monkeypatch.setattr(
        service,
        "_persist_debug_history_session_document",
        fail_worker_history_persist,
    )

    result = service.start_debug_session_async(
        graph_document_payload=None,
        settle_timeout_ms=500,
    )
    session_id = result["debug_session"]["session_id"]

    assert result["debug_session"]["status"] == "failed"
    assert result["debug_session"]["paused_reason"] == "debug_worker_failed"
    assert result["debug_session"]["last_control_action"] == "worker_failed"
    assert session_id not in service._debug_execution_threads  # type: ignore[attr-defined]
    assert session_id not in service._debug_runtime_contexts  # type: ignore[attr-defined]


def test_shutdown_debug_sessions_reports_worker_timeout() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service._debug_execution_threads[session_id] = _AliveThread()  # type: ignore[attr-defined]

    try:
        with pytest.raises(TimeoutError, match=session_id):
            service.shutdown_debug_sessions(
                reason="application_shutdown",
                timeout_seconds=0,
            )
    finally:
        service._debug_execution_threads.pop(session_id, None)  # type: ignore[attr-defined]
        service.abort_debug_session(session_id=session_id, reason="test_cleanup")


@pytest.mark.parametrize(
    "action_name",
    [
        "continue_debug_session_async",
        "step_over_debug_session_async",
        "step_into_debug_session_async",
    ],
)
def test_async_debug_control_rolls_back_when_worker_cannot_restart(
    action_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service._release_debug_runtime_context(session_id)  # type: ignore[attr-defined]
    previous_session = service.get_debug_session(session_id=session_id)
    monkeypatch.setattr(service, "_launch_debug_execution_thread", lambda **_: False)

    action = getattr(service, action_name)
    with pytest.raises(ValueError, match="debug execution worker could not be started"):
        action(session_id=session_id)

    current_session = service.get_debug_session(session_id=session_id)
    assert current_session["debug_session"] == previous_session["debug_session"]
    assert current_session["debug_events"] == previous_session["debug_events"]


def test_start_debug_session_async_keeps_request_status_when_execution_is_still_preparing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_minimal_workspace_graph())

    def keep_execution_thread_alive(*, session_id: str) -> bool:
        service._debug_execution_threads[session_id] = _AliveThread()  # type: ignore[attr-defined]
        return True

    monkeypatch.setattr(service, "_launch_debug_execution_thread", keep_execution_thread_alive)

    start_result = service.start_debug_session_async(
        graph_document_payload=None,
        settle_timeout_ms=0,
    )

    assert start_result["status"] == "started"
    assert start_result["debug_session"]["status"] == "preparing"


def test_step_async_waits_for_initial_pause_before_validating_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    session_document = service.get_debug_session(session_id=session_id)
    session_document["debug_session"] = {
        **session_document["debug_session"],
        "status": "running",
        "paused_reason": None,
        "last_control_action": None,
        "step_sequence": 0,
    }
    session_document["debug_events"] = []
    session_document["debug_keyframes"] = []
    session_document["debug_snapshots"] = []
    service._replace_debug_session_document(  # type: ignore[attr-defined]
        session_document,
        persist_history=False,
    )
    service._debug_execution_threads[session_id] = _AliveThread()  # type: ignore[attr-defined]

    settle_calls: list[int] = []

    def settle_initial_pause(*, session_id: str, settle_timeout_ms: int, **_: object) -> dict:
        settle_calls.append(settle_timeout_ms)
        settled = service.get_debug_session(session_id=session_id)
        settled["debug_session"] = {
            **settled["debug_session"],
            "status": "paused",
            "paused_reason": "breakpoint_hit",
        }
        service._replace_debug_session_document(  # type: ignore[attr-defined]
            settled,
            persist_history=False,
        )
        return {**settled, "status": "paused"}

    monkeypatch.setattr(service, "_await_debug_execution_settle", settle_initial_pause)
    monkeypatch.setattr(service, "_signal_debug_execution_thread", lambda _: True)

    try:
        result = service.step_into_debug_session_async(session_id=session_id)
    finally:
        service._release_debug_runtime_context(session_id)  # type: ignore[attr-defined]

    assert result["debug_session"]["status"] == "paused"
    assert result["debug_session"]["step_mode"] == "step_into"
    assert len(settle_calls) == 2
    assert settle_calls[0] >= 500


def test_continue_debug_session_rejects_after_terminal_completion() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_step_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    assert start_result["debug_session"]["status"] == "paused"
    first_continue = service.continue_debug_session(session_id=session_id)
    assert first_continue["debug_session"]["status"] == "paused"
    completed_result = service.continue_debug_session(session_id=session_id)
    assert completed_result["debug_session"]["status"] == "completed"
    with pytest.raises(ValueError, match="debug session already in terminal status: completed"):
        service.continue_debug_session(session_id=session_id)


def test_continue_debug_session_rejects_after_terminal_failure() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_python_only_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service._remember_debug_session(  # type: ignore[attr-defined]
        {
            "request": start_result["request"],
            "debug_session": {
                **start_result["debug_session"],
                "session_id": session_id,
                "status": "failed",
                "completed_at": "2026-07-01T16:00:00+00:00",
                "last_control_action": "continue",
            },
            "stage_timeline": start_result["stage_timeline"],
            "object_index": start_result["object_index"],
            "diagnostic_links": start_result["diagnostic_links"],
            "runtime_preview": start_result["runtime_preview"],
            "runtime_preview_summary": start_result["runtime_preview_summary"],
            "variable_snapshot": {"value": 1},
            "debug_events": [
                {
                    "event_kind": "diagnostic.raised",
                    "node_id": "node-run-python",
                    "error_code": "python.execution_failed",
                    "message": "python child failed",
                }
            ],
            "debug_keyframes": [],
        }
    )

    with pytest.raises(ValueError, match="debug session already in terminal status: failed"):
        service.continue_debug_session(session_id=session_id)


def test_debug_node_failure_pauses_with_exception_reason_and_can_abort() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_python_only_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    assert start_result["status"] == "started"
    assert start_result["debug_session"]["status"] == "paused"
    assert start_result["debug_session"]["paused_reason"] == "exception_raised"
    assert start_result["runtime_preview"]["current_node"]["node_id"] == "node-run-python"
    diagnostic_events = [
        item
        for item in service.list_debug_session_events(session_id=session_id)["events"]
        if item.get("event_kind") == "diagnostic.raised"
    ]
    assert diagnostic_events
    assert isinstance(diagnostic_events[-1]["error_code"], str)
    assert diagnostic_events[-1]["error_code"].startswith("python.")

    abort_result = service.abort_debug_session(session_id=session_id, reason="debug_exception_abort")
    assert abort_result["debug_session"]["status"] == "aborted"
    assert abort_result["debug_session"]["paused_reason"] == "debug_exception_abort"


def test_apply_debug_session_variables_updates_session_document_in_staged_mode() -> None:
    service = CompilationWorkbenchService()
    graph = _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    graph["nodes"][0]["node_config"]["initial_variables"]["retry_count"] = 0
    service.save_graph_document(graph)

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    apply_result = service.apply_debug_session_variables(
        session_id=session_id,
        updates={
            "username": "debug-user",
            "retry_count": 3,
        },
        apply_mode="staged",
    )

    assert apply_result["debug_session"]["session_id"] == session_id
    assert apply_result["variable_snapshot"]["username"] == "original-user"
    assert apply_result["variable_snapshot"]["retry_count"] == 0
    assert apply_result["debug_session"]["pending_variable_overrides"] == {
        "username": "debug-user",
        "retry_count": 3,
    }
    reloaded_session = service.get_debug_session(session_id=session_id)
    assert reloaded_session["debug_session"]["pending_variable_overrides"] == {
        "username": "debug-user",
        "retry_count": 3,
    }
    assert reloaded_session["variable_changes"]["username"]["pending"] is True
    assert reloaded_session["variable_changes"]["username"]["original_value"] == "original-user"


def test_apply_debug_session_variables_in_immediate_mode_does_not_leave_pending_overrides() -> None:
    service = CompilationWorkbenchService()
    graph = _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    graph["nodes"][0]["node_config"]["initial_variables"]["retry_count"] = 0
    service.save_graph_document(graph)

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    apply_result = service.apply_debug_session_variables(
        session_id=session_id,
        updates={
            "username": "immediate-user",
            "retry_count": 5,
        },
        apply_mode="immediate",
    )

    assert apply_result["debug_session"]["session_id"] == session_id
    assert apply_result["debug_session"]["variable_apply_mode"] == "immediate"
    assert apply_result["variable_snapshot"]["username"] == "immediate-user"
    assert apply_result["variable_snapshot"]["retry_count"] == 5
    assert apply_result["debug_session"]["pending_variable_overrides"] == {}

    reloaded_session = service.get_debug_session(session_id=session_id)
    assert reloaded_session["debug_session"]["pending_variable_overrides"] == {}
    assert reloaded_session["variable_snapshot"]["username"] == "immediate-user"
    assert reloaded_session["variable_snapshot"]["retry_count"] == 5


def test_debug_session_inherits_variable_apply_mode_from_software_preferences() -> None:
    configuration_service = _build_test_configuration_service()
    _update_test_configuration(
        configuration_service,
        section="python_runtime_settings",
        values={"variable_apply_mode": "immediate"},
    )
    service = CompilationWorkbenchService(configuration_service=configuration_service)
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session(graph_document_payload=None)

    assert start_result["debug_session"]["variable_apply_mode"] == "immediate"
    assert start_result["variable_descriptors"]["username"] == {
        "name": "username",
        "value_type": "string",
        "scope": "global",
        "editable": True,
        "origin": "flow.start.initial_variables",
        "nullable": False,
    }


def test_apply_debug_session_variables_rejects_unknown_variable() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    start_result = service.start_debug_session(graph_document_payload=None)

    with pytest.raises(ValueError, match="debug variable does not exist: missing"):
        service.apply_debug_session_variables(
            session_id=start_result["debug_session"]["session_id"],
            updates={"missing": "value"},
            apply_mode="staged",
        )


def test_apply_debug_session_variables_rejects_type_mismatch() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    start_result = service.start_debug_session(graph_document_payload=None)

    with pytest.raises(
        ValueError,
        match="debug variable type mismatch for username: expected string",
    ):
        service.apply_debug_session_variables(
            session_id=start_result["debug_session"]["session_id"],
            updates={"username": {"invalid": True}},
            apply_mode="immediate",
        )


def test_save_graph_document_is_blocked_while_debug_session_is_active() -> None:
    service = CompilationWorkbenchService()
    graph_payload = _build_debug_step_workspace_graph()
    service.save_graph_document(graph_payload)
    start_result = service.start_debug_session(graph_document_payload=None)

    assert start_result["debug_session"]["status"] == "paused"
    with pytest.raises(
        ValueError,
        match="graph mutation blocked while debug session is active: operation=save_graph_document",
    ):
        service.save_graph_document(graph_payload)


def test_build_graph_node_draft_is_blocked_while_debug_session_is_active() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_step_workspace_graph())
    start_result = service.start_debug_session(graph_document_payload=None)

    assert start_result["debug_session"]["status"] == "paused"
    with pytest.raises(
        ValueError,
        match="graph mutation blocked while debug session is active: operation=build_graph_node_draft",
    ):
        service.build_graph_node_draft(resource_key="data.set_variable")


def test_debug_history_sessions_are_persisted_under_project_storage_root(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))
    project_path = tmp_path / "debug-history-project.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service.continue_debug_session(session_id=session_id)

    history_payload = service.list_debug_history_sessions()

    assert history_payload["sessions"][0]["session_id"] == session_id
    history_file = history_payload["sessions"][0]["history_file"]
    assert history_file == session_id
    assert (
        project_path.parent
        / "debug-history-project.weconduct.data"
        / "debug-history"
        / "sessions"
        / history_file
        / "manifest.json"
    ).exists()


def test_open_debug_history_session_reads_persisted_history_payload(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_debug_step_workspace_graph())
    project_path = tmp_path / "debug-history-open.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service.continue_debug_session(session_id=session_id)
    service.continue_debug_session(session_id=session_id)

    open_payload = service.open_debug_history_session(session_id=session_id)

    assert open_payload["source"] == "history_store"
    assert open_payload["session_id"] == session_id
    assert open_payload["session"]["debug_session"]["session_id"] == session_id
    assert open_payload["session"]["debug_session"]["status"] == "completed"


def test_get_debug_live_projection_maps_runtime_preview_node_states() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    projection_payload = service.get_debug_live_projection(session_id=session_id)

    assert projection_payload["projection"]["mode"] == "live"
    assert projection_payload["projection"]["paused_node_id"] == "node-start"
    assert projection_payload["projection"]["node_status_by_id"]["node-start"] == "paused"
    assert projection_payload["projection"]["record_frame_node_ids"] == []
    assert projection_payload["projection"]["skipped_node_ids"] == []


def test_get_debug_history_projection_maps_persisted_runtime_preview(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_minimal_workspace_graph())
    project_path = tmp_path / "debug-history-projection.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    session_document = {
        "request": start_result["request"],
        "debug_session": {
            **start_result["debug_session"],
            "session_id": session_id,
            "status": "paused",
        },
        "stage_timeline": start_result["stage_timeline"],
        "object_index": start_result["object_index"],
        "runtime_plan": start_result["runtime_plan"],
        "diagnostic_links": start_result["diagnostic_links"],
        "runtime_preview": {
            "scheduler_mode": "static",
            "active_paths": [["node-start", "node-branch-a"]],
            "queued_node_ids": ["node-branch-a"],
            "executed_node_ids": ["node-start"],
            "current_node": {
                "node_id": "node-paused",
                "node_kind": "browser.click",
                "repeat_mode": False,
            },
            "join_buffers": {},
            "retry_states": {},
        },
        "runtime_preview_summary": {
            "scheduler_mode": "static",
            "queued_node_count": 1,
            "executed_node_count": 1,
            "join_buffer_count": 0,
            "retry_state_count": 0,
            "current_node_id": "node-paused",
        },
        "variable_snapshot": {"username": "history-user"},
        "debug_events": [
            {
                "event_kind": "record_frame.hit",
                "node_id": "node-start",
                "frame_identity": "rf-1",
            },
            {
                "event_kind": "node.skipped",
                "node_id": "node-never-reached",
                "reason": "unreachable",
            },
        ],
    }
    service._replace_debug_session_document(session_document)  # type: ignore[attr-defined]

    history_projection = service.get_debug_history_projection(session_id=session_id)

    assert history_projection["source"] == "history_store"
    assert history_projection["projection"]["mode"] == "history"
    assert history_projection["projection"]["node_status_by_id"]["node-start"] == "completed"
    assert history_projection["projection"]["node_status_by_id"]["node-branch-a"] == "waiting"
    assert history_projection["projection"]["node_status_by_id"]["node-paused"] == "paused"
    assert history_projection["projection"]["active_paths"] == [["node-start", "node-branch-a"]]
    assert history_projection["projection"]["record_frame_node_ids"] == ["node-start"]
    assert history_projection["projection"]["skipped_node_ids"] == ["node-never-reached"]


def test_terminal_history_projection_preserves_selected_pause_event_marker(
    tmp_path: Path,
) -> None:
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(tmp_path / "runtime" / "workspace-state.json"),
    )
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    service.save_project_as(project_path=str(tmp_path / "debug-history-pause-marker.weconduct.json"))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    paused_event = next(
        item
        for item in service.list_debug_session_events(session_id=session_id)["events"]
        if item.get("event_kind") == "debug.paused"
    )
    service.continue_debug_session(session_id=session_id)

    history_projection = service.get_debug_history_projection(
        session_id=session_id,
        event_index=paused_event["event_index"],
    )

    assert service.open_debug_history_session(session_id=session_id)["session"]["debug_session"]["status"] == "completed"
    assert history_projection["projection"]["paused_node_id"] == "node-start"
    assert history_projection["projection"]["node_status_by_id"]["node-start"] == "paused"
    assert "debug_result" not in history_projection["variable_snapshot"]


def test_get_debug_history_projection_preserves_iteration_stack_for_loop_hits(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_debug_while_workspace_graph())
    project_path = tmp_path / "debug-history-loop.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service.continue_debug_session(session_id=session_id)
    service.continue_debug_session(session_id=session_id)

    history_projection = service.get_debug_history_projection(session_id=session_id)
    history_payload = service.open_debug_history_session(session_id=session_id)

    breakpoint_events = [
        item
        for item in history_payload["session"]["events"]
        if isinstance(item, dict)
        and item.get("event_kind") == "breakpoint.hit"
        and item.get("node_id") == "node-loop-body"
    ]

    assert len(breakpoint_events) >= 2
    assert breakpoint_events[0].get("iteration_stack") != breakpoint_events[1].get("iteration_stack")
    assert breakpoint_events[0].get("iteration_stack") == ["node-while:1"]
    assert breakpoint_events[1].get("iteration_stack") == ["node-while:2"]
    assert history_projection["projection"]["mode"] == "history"
    assert "node-loop-body" in history_projection["projection"]["node_status_by_id"]


def test_failed_debug_session_is_persisted_into_history_summary_and_payload(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_python_only_workspace_graph())
    project_path = tmp_path / "debug-failed-history.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    service._replace_debug_session_document(  # type: ignore[attr-defined]
        {
            "request": start_result["request"],
            "debug_session": {
                **start_result["debug_session"],
                "session_id": session_id,
                "status": "failed",
                "completed_at": "2026-07-01T16:00:00+00:00",
                "paused_reason": None,
                "last_control_action": "continue",
            },
            "stage_timeline": start_result["stage_timeline"],
            "object_index": start_result["object_index"],
            "runtime_plan": start_result["runtime_plan"],
            "diagnostic_links": [
                {
                    "diagnostic_id": "runtime:debug-failed:0",
                    "category": "python.execution_failed",
                    "severity": "error",
                    "message": "python child failed",
                    "graph_ref": {"node_id": "node-run-python"},
                }
            ],
            "runtime_preview": {
                "scheduler_mode": "flow_graph",
                "active_paths": [],
                "queued_node_ids": [],
                "executed_node_ids": ["node-start"],
                "current_node": {
                    "node_id": "node-run-python",
                    "node_kind": "python.run",
                    "repeat_mode": False,
                    "graph_model_id": "graph:workspace",
                    "iteration_stack": [],
                },
                "join_buffers": {},
                "retry_states": {},
            },
            "runtime_preview_summary": {
                "scheduler_mode": "flow_graph",
                "queued_node_count": 0,
                "executed_node_count": 1,
                "join_buffer_count": 0,
                "retry_state_count": 0,
                "current_node_id": "node-run-python",
            },
            "variable_snapshot": {"value": 1},
            "debug_events": [
                {
                    "event_kind": "diagnostic.raised",
                    "node_id": "node-run-python",
                    "error_code": "python.execution_failed",
                    "message": "python child failed",
                }
            ],
            "debug_keyframes": [],
        }
    )

    history_payload = service.list_debug_history_sessions()
    open_payload = service.open_debug_history_session(session_id=session_id)
    projection_payload = service.get_debug_history_projection(session_id=session_id)

    assert history_payload["sessions"][0]["session_id"] == session_id
    assert history_payload["sessions"][0]["status"] == "failed"
    assert open_payload["session"]["debug_session"]["status"] == "failed"
    assert open_payload["session"]["runtime_preview_summary"]["current_node_id"] == "node-run-python"
    assert projection_payload["projection"]["mode"] == "history"
    assert projection_payload["projection"]["node_status_by_id"]["node-run-python"] == "running"
    assert projection_payload["projection"]["node_status_by_id"]["node-start"] == "completed"


def test_debug_step_action_records_control_metadata() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    step_result = service.step_over_debug_session(session_id=session_id)

    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == "step_over"
    assert step_result["debug_session"]["paused_reason"] == "step_completed"
    assert step_result["debug_session"]["last_control_action"] == "step_over"
    assert step_result["debug_session"]["step_sequence"] == 1


def test_step_over_executes_current_node_and_pauses_at_next_breakpoint() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_step_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    first_step = service.step_over_debug_session(session_id=session_id)
    assert first_step["debug_session"]["status"] == "paused"
    assert first_step["debug_session"]["paused_reason"] == "step_completed"
    assert first_step["runtime_preview"]["current_node"]["node_id"] == "node-set-variable"

    step_result = service.step_over_debug_session(session_id=session_id)

    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == "step_over"
    assert step_result["runtime_preview"]["current_node"]["node_id"] == "node-after"
    assert step_result["runtime_preview"]["executed_node_ids"] == [
        "node-start",
        "node-set-variable",
    ]
    assert step_result["variable_snapshot"]["step_value"] == "after"


def test_step_into_on_regular_node_matches_step_over_behavior() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_step_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    first_step = service.step_over_debug_session(session_id=session_id)
    assert first_step["runtime_preview"]["current_node"]["node_id"] == "node-set-variable"

    step_result = service.step_into_debug_session(session_id=session_id)

    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == "step_into"
    assert step_result["runtime_preview"]["current_node"]["node_id"] == "node-after"
    assert step_result["variable_snapshot"]["step_value"] == "after"


def test_step_out_is_disabled_on_top_level_graph() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_step_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    with pytest.raises(
        ValueError,
        match="debug step_out is only available inside a component",
    ):
        service.step_out_debug_session(session_id=session_id)


def test_continue_pauses_after_node_when_breakpoint_timing_is_after() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_after_breakpoint_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    continue_result = service.continue_debug_session(session_id=session_id)

    assert continue_result["debug_session"]["status"] == "paused"
    assert continue_result["debug_session"]["paused_reason"] == "breakpoint_hit"
    assert continue_result["runtime_preview"]["executed_node_ids"] == [
        "node-start",
        "node-after-breakpoint",
    ]
    assert continue_result["runtime_preview"]["current_node"]["node_id"] == "node-after-breakpoint"
    assert continue_result["variable_snapshot"]["after_test_value"] == "after"


def test_step_over_on_custom_node_graph_skips_internal_breakpoints_and_pauses_after_component() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_custom_node_graph_for_debug_step())
    save_result = service.save_custom_node_graph_resource(resource_name="调试子图组件")
    resource_key = save_result["resource"]["resource_key"]
    service.save_graph_document(_build_parent_graph_using_debug_step_component(resource_key))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    first_step = service.step_over_debug_session(session_id=session_id)
    assert first_step["runtime_preview"]["current_node"]["node_id"] == "node-component-call"

    step_result = service.step_over_debug_session(session_id=session_id)

    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == "step_over"
    assert step_result["runtime_preview"]["current_node"]["node_id"] == "node-after-component"
    assert step_result["variable_snapshot"]["component_value"] == "inside-component"
    events_payload = service.list_debug_session_events(session_id=session_id)
    assert not any(
        item.get("node_id") == "component-inner-step" and item.get("event_kind") == "breakpoint.hit"
        for item in events_payload["events"]
    )


def test_step_into_on_custom_node_graph_enters_internal_breakpoint() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_custom_node_graph_for_debug_step())
    save_result = service.save_custom_node_graph_resource(resource_name="调试子图组件")
    resource_key = save_result["resource"]["resource_key"]
    service.save_graph_document(_build_parent_graph_using_debug_step_component(resource_key))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    first_step = service.step_over_debug_session(session_id=session_id)
    assert first_step["runtime_preview"]["current_node"]["node_id"] == "node-component-call"

    step_result = service.step_into_debug_session(session_id=session_id)

    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == "step_into"
    assert step_result["runtime_preview"]["current_node"]["node_id"] == "component-inner-step"
    events_payload = service.list_debug_session_events(session_id=session_id)
    assert any(
        item.get("node_id") == "component-inner-step" and item.get("event_kind") == "breakpoint.hit"
        for item in events_payload["events"]
    )


def test_step_out_on_custom_node_graph_resumes_to_parent_after_component() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_custom_node_graph_for_debug_step())
    save_result = service.save_custom_node_graph_resource(resource_name="调试子图组件")
    resource_key = save_result["resource"]["resource_key"]
    service.save_graph_document(_build_parent_graph_using_debug_step_component(resource_key))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    first_step = service.step_over_debug_session(session_id=session_id)
    assert first_step["runtime_preview"]["current_node"]["node_id"] == "node-component-call"
    into_result = service.step_into_debug_session(session_id=session_id)
    assert into_result["runtime_preview"]["current_node"]["node_id"] == "component-inner-step"

    step_result = service.step_out_debug_session(session_id=session_id)

    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == "step_out"
    assert step_result["runtime_preview"]["current_node"]["node_id"] == "node-after-component"
    assert step_result["variable_snapshot"]["component_value"] == "inside-component"


def test_step_into_on_custom_node_graph_pauses_after_internal_node_when_breakpoint_timing_is_after() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_custom_node_graph_for_debug_after_step())
    save_result = service.save_custom_node_graph_resource(resource_name="调试子图组件-after")
    resource_key = save_result["resource"]["resource_key"]
    service.save_graph_document(_build_parent_graph_using_debug_step_component(resource_key))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    first_step = service.step_over_debug_session(session_id=session_id)
    assert first_step["runtime_preview"]["current_node"]["node_id"] == "node-component-call"

    step_result = service.step_into_debug_session(session_id=session_id)

    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == "step_into"
    assert step_result["runtime_preview"]["current_node"]["node_id"] == "component-inner-step"
    assert step_result["variable_snapshot"]["component_value"] == "inside-component"
    events_payload = service.list_debug_session_events(session_id=session_id)
    assert any(
        item.get("node_id") == "component-inner-step"
        and item.get("event_kind") == "breakpoint.hit"
        and item.get("pause_timing") == "after"
        for item in events_payload["events"]
    )


def test_step_over_on_custom_node_graph_skips_internal_after_breakpoint_and_pauses_after_component() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_custom_node_graph_for_debug_after_step())
    save_result = service.save_custom_node_graph_resource(resource_name="调试子图组件-after-step-over")
    resource_key = save_result["resource"]["resource_key"]
    service.save_graph_document(_build_parent_graph_using_debug_step_component(resource_key))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    first_step = service.step_over_debug_session(session_id=session_id)
    assert first_step["runtime_preview"]["current_node"]["node_id"] == "node-component-call"

    step_result = service.step_over_debug_session(session_id=session_id)

    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == "step_over"
    assert step_result["runtime_preview"]["current_node"]["node_id"] == "node-after-component"
    events_payload = service.list_debug_session_events(session_id=session_id)
    assert not any(
        item.get("node_id") == "component-inner-step"
        and item.get("event_kind") == "breakpoint.hit"
        and item.get("pause_timing") == "after"
        for item in events_payload["events"]
    )


def test_step_out_on_nested_custom_node_graph_resumes_to_parent_after_outer_component() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_custom_node_graph_for_debug_step())
    inner_save_result = service.save_custom_node_graph_resource(resource_name="内部调试子图组件")
    inner_resource_key = inner_save_result["resource"]["resource_key"]
    service.save_graph_document(_build_nested_custom_node_graph_for_debug_step(inner_resource_key))
    outer_save_result = service.save_custom_node_graph_resource(resource_name="外层调试子图组件")
    outer_resource_key = outer_save_result["resource"]["resource_key"]
    service.save_graph_document(_build_parent_graph_using_debug_step_component(outer_resource_key))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    first_step = service.step_over_debug_session(session_id=session_id)
    assert first_step["runtime_preview"]["current_node"]["node_id"] == "node-component-call"
    into_result = service.step_into_debug_session(session_id=session_id)
    assert into_result["runtime_preview"]["current_node"]["node_id"] == "component-inner-step"

    step_result = service.step_out_debug_session(session_id=session_id)

    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == "step_out"
    assert step_result["runtime_preview"]["current_node"]["node_id"] == "node-after-component"


def test_loop_breakpoint_hits_have_distinct_frame_identity_between_iterations() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_while_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    first_break = service.continue_debug_session(session_id=session_id)
    assert first_break["runtime_preview"]["current_node"]["node_id"] == "node-loop-body"

    second_break = service.continue_debug_session(session_id=session_id)
    assert second_break["runtime_preview"]["current_node"]["node_id"] == "node-loop-body"

    events_payload = service.list_debug_session_events(session_id=session_id)
    breakpoint_events = [
        item
        for item in events_payload["events"]
        if item.get("event_kind") == "breakpoint.hit" and item.get("node_id") == "node-loop-body"
    ]

    assert len(breakpoint_events) >= 2
    assert breakpoint_events[0].get("frame_identity") != breakpoint_events[1].get("frame_identity")


def test_loop_breakpoint_hits_expose_iteration_stack_between_iterations() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_while_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service.continue_debug_session(session_id=session_id)
    service.continue_debug_session(session_id=session_id)

    events_payload = service.list_debug_session_events(session_id=session_id)
    breakpoint_events = [
        item
        for item in events_payload["events"]
        if item.get("event_kind") == "breakpoint.hit" and item.get("node_id") == "node-loop-body"
    ]

    assert len(breakpoint_events) >= 2
    assert breakpoint_events[0].get("iteration_stack") != breakpoint_events[1].get("iteration_stack")
    assert breakpoint_events[0].get("iteration_stack") == ["node-while:1"]
    assert breakpoint_events[1].get("iteration_stack") == ["node-while:2"]


def test_step_out_on_triple_nested_custom_node_graph_resumes_to_parent_after_outer_component() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_custom_node_graph_for_debug_step())
    inner_save_result = service.save_custom_node_graph_resource(resource_name="最内层调试子图组件")
    inner_resource_key = inner_save_result["resource"]["resource_key"]
    service.save_graph_document(_build_nested_custom_node_graph_for_debug_step(inner_resource_key))
    middle_save_result = service.save_custom_node_graph_resource(resource_name="中间调试子图组件")
    middle_resource_key = middle_save_result["resource"]["resource_key"]
    service.save_graph_document(_build_triple_nested_custom_node_graph_for_debug_step(middle_resource_key))
    outer_save_result = service.save_custom_node_graph_resource(resource_name="最外层调试子图组件")
    outer_resource_key = outer_save_result["resource"]["resource_key"]
    service.save_graph_document(_build_parent_graph_using_debug_step_component(outer_resource_key))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    first_step = service.step_over_debug_session(session_id=session_id)
    assert first_step["runtime_preview"]["current_node"]["node_id"] == "node-component-call"
    into_result = service.step_into_debug_session(session_id=session_id)
    assert into_result["runtime_preview"]["current_node"]["node_id"] == "component-inner-step"

    step_result = service.step_out_debug_session(session_id=session_id)

    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == "step_out"
    assert step_result["runtime_preview"]["current_node"]["node_id"] == "node-after-component"


def test_open_debug_history_session_preserves_nested_component_call_stack(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_custom_node_graph_for_debug_step())
    inner_save_result = service.save_custom_node_graph_resource(resource_name="内部历史调试子图组件")
    inner_resource_key = inner_save_result["resource"]["resource_key"]
    service.save_graph_document(_build_nested_custom_node_graph_for_debug_step(inner_resource_key))
    outer_save_result = service.save_custom_node_graph_resource(resource_name="外层历史调试子图组件")
    outer_resource_key = outer_save_result["resource"]["resource_key"]
    service.save_graph_document(_build_parent_graph_using_debug_step_component(outer_resource_key))
    project_path = tmp_path / "debug-history-nested-component.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service.continue_debug_session(session_id=session_id)

    history_payload = service.open_debug_history_session(session_id=session_id)
    component_call_stack = history_payload["session"]["runtime_preview"]["current_node"]["component_call_stack"]

    assert history_payload["session"]["debug_session"]["status"] == "paused"
    assert component_call_stack == [outer_resource_key, inner_resource_key]


def test_open_debug_history_session_preserves_parallel_component_call_stack(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_custom_node_graph_for_debug_step())
    inner_save_result = service.save_custom_node_graph_resource(resource_name="并行历史调试子图组件")
    inner_resource_key = inner_save_result["resource"]["resource_key"]
    service.save_graph_document(_build_parallel_custom_node_graph_for_debug_history(inner_resource_key))
    outer_save_result = service.save_custom_node_graph_resource(resource_name="并行外层历史调试子图组件")
    outer_resource_key = outer_save_result["resource"]["resource_key"]
    service.save_graph_document(_build_parent_graph_using_debug_step_component(outer_resource_key))
    project_path = tmp_path / "debug-history-parallel-component.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service.continue_debug_session(session_id=session_id)

    history_payload = service.open_debug_history_session(session_id=session_id)
    runtime_preview = history_payload["session"]["runtime_preview"]

    assert history_payload["session"]["debug_session"]["status"] == "paused"
    assert runtime_preview["current_node"]["component_call_stack"] == [outer_resource_key, inner_resource_key]
    assert runtime_preview["current_node"]["node_id"] == "component-inner-step"


def test_continue_pauses_when_breakpoint_expression_evaluates_true() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_step_workspace_graph_with_condition_expression_breakpoint())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    continue_result = service.continue_debug_session(session_id=session_id)

    assert continue_result["debug_session"]["status"] == "paused"
    assert continue_result["runtime_preview"]["current_node"]["node_id"] == "node-after"
    events_payload = service.list_debug_session_events(session_id=session_id)
    assert any(
        item.get("node_id") == "node-after"
        and item.get("event_kind") == "breakpoint.hit"
        for item in events_payload["events"]
    )


def test_continue_skips_breakpoint_when_expression_evaluates_false() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_step_workspace_graph_with_false_condition_expression_breakpoint()
    )

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    continue_result = service.continue_debug_session(session_id=session_id)

    assert continue_result["debug_session"]["status"] == "completed"
    events_payload = service.list_debug_session_events(session_id=session_id)
    assert not any(
        item.get("node_id") == "node-after"
        and item.get("event_kind") == "breakpoint.hit"
        for item in events_payload["events"]
    )


def test_continue_pauses_on_second_hit_when_breakpoint_hit_count_is_two() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_loop_workspace_graph_with_breakpoint_hit_count(2))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    continue_result = service.continue_debug_session(session_id=session_id)

    assert continue_result["debug_session"]["status"] == "paused"
    breakpoint_events = [
        item
        for item in service.list_debug_session_events(session_id=session_id)["events"]
        if item.get("event_kind") == "breakpoint.hit" and item.get("node_id") == "node-loop-body"
    ]
    assert len(breakpoint_events) == 1
    assert breakpoint_events[0]["breakpoint_hit_ordinal_in_session"] == 2
    assert breakpoint_events[0]["iteration_stack"] == ["node-while:2"]


def test_continue_once_breakpoint_only_pauses_on_first_iteration() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_loop_workspace_graph_with_once_breakpoint())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    first_continue = service.continue_debug_session(session_id=session_id)
    second_continue = service.continue_debug_session(session_id=session_id)

    assert first_continue["debug_session"]["status"] == "paused"
    assert second_continue["debug_session"]["status"] == "completed"
    breakpoint_events = [
        item
        for item in service.list_debug_session_events(session_id=session_id)["events"]
        if item.get("event_kind") == "breakpoint.hit" and item.get("node_id") == "node-loop-body"
    ]
    assert len(breakpoint_events) == 1
    assert breakpoint_events[0]["iteration_stack"] == ["node-while:1"]


def test_record_debug_breakpoint_hit_persists_event_into_history_store(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_minimal_workspace_graph())
    project_path = tmp_path / "debug-events.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    record_result = service.record_debug_breakpoint_hit(
        session_id=session_id,
        node_id="node-start",
        instance_path=["graph:workspace", "node-start"],
        pause_timing="before",
        iteration_stack=[],
    )

    assert record_result["event"]["event_kind"] == "breakpoint.hit"
    assert record_result["event"]["breakpoint_hit_ordinal_in_session"] == 1

    history_payload = service.open_debug_history_session(session_id=session_id)
    history_events = history_payload["session"]["events"]
    history_snapshots = history_payload["session"]["snapshots"]

    assert history_events[-1]["event_kind"] == "breakpoint.hit"
    assert history_events[-1]["node_id"] == "node-start"
    assert history_events[-1]["breakpoint_hit_ordinal_in_session"] == 1
    assert history_snapshots[-1]["event_kind"] == "breakpoint.hit"
    assert history_snapshots[-1]["snapshot_id"]


def test_automatic_record_frame_persists_event_into_history_store(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(
        _build_debug_execution_workspace_graph(record_frame_on_set_variable=True)
    )
    project_path = tmp_path / "debug-record-frame.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    history_payload = service.open_debug_history_session(session_id=session_id)
    history_events = history_payload["session"]["events"]
    history_keyframes = history_payload["session"]["keyframes"]
    history_snapshots = history_payload["session"]["snapshots"]

    record_events = [item for item in history_events if item.get("event_kind") == "record_frame.hit"]
    record_keyframes = [item for item in history_keyframes if item.get("event_kind") == "record_frame.hit"]
    assert record_events[-1]["node_id"] == "node-set-variable"
    assert record_events[-1]["record_frame_ordinal_in_session"] == 1
    assert record_keyframes[-1]["node_id"] == "node-set-variable"
    assert history_snapshots[-1]["event_kind"] == "record_frame.hit"
    assert history_snapshots[-1]["snapshot_id"]


def test_list_debug_session_events_reads_persisted_history_events(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(
        _build_debug_execution_workspace_graph(record_frame_on_set_variable=True)
    )
    project_path = tmp_path / "debug-event-list.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    events_payload = service.list_debug_session_events(session_id=session_id)

    assert events_payload["session_id"] == session_id
    assert events_payload["source"] == "history_store"
    assert events_payload["total_count"] >= 1
    assert any(item["event_kind"] == "record_frame.hit" for item in events_payload["events"])


def test_list_debug_session_events_does_not_overlay_active_session_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(tmp_path / "runtime" / "workspace-state.json"),
    )
    service.save_graph_document(_build_minimal_workspace_graph())
    service.save_project_as(project_path=str(tmp_path / "immutable-history.weconduct.json"))
    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    monkeypatch.setattr(
        service,
        "_find_active_debug_session_optional",
        lambda _: {
            **start_result,
            "debug_events": [
                *start_result.get("debug_events", []),
                {"event_kind": "injected.live.event", "event_id": "live-only"},
            ],
        },
        raising=False,
    )

    events_payload = service.list_debug_session_events(session_id=session_id)

    assert all(
        event.get("event_kind") != "injected.live.event"
        for event in events_payload["events"]
    )


def test_request_debug_pause_rejects_already_paused_session(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    project_path = tmp_path / "debug-pause-auto-context.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    with pytest.raises(
        ValueError,
        match="debug pause is not allowed for session status: paused",
    ):
        service.request_debug_pause(
            session_id=session_id,
            node_id=None,
            reason="manual_pause",
        )


def test_request_debug_pause_rejects_running_session_without_execution_thread(
    tmp_path: Path,
) -> None:
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(tmp_path / "runtime" / "workspace-state.json"),
    )
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    service.save_project_as(project_path=str(tmp_path / "debug-pause-no-thread.weconduct.json"))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    session_document = service.get_debug_session(session_id=session_id)
    session_document["debug_session"] = {
        **session_document["debug_session"],
        "status": "running",
        "paused_reason": None,
    }
    service._replace_debug_session_document(session_document)  # type: ignore[attr-defined]
    service._debug_execution_threads.pop(session_id, None)  # type: ignore[attr-defined]
    events_before = service.list_debug_session_events(session_id=session_id)["events"]

    with pytest.raises(ValueError, match="debug pause requires an active execution thread"):
        service.request_debug_pause(
            session_id=session_id,
            node_id=None,
            reason="manual_pause",
        )

    events_after = service.list_debug_session_events(session_id=session_id)["events"]
    assert events_after == events_before


def test_continue_debug_session_persists_resumed_event(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    project_path = tmp_path / "debug-resume.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    continue_result = service.continue_debug_session(session_id=session_id)

    assert continue_result["debug_session"]["status"] == "completed"
    assert continue_result["debug_session"]["last_control_action"] == "continue"
    assert continue_result["runtime_preview"]["executed_node_ids"] == [
        "node-start",
        "node-set-variable",
    ]

    events_payload = service.list_debug_session_events(session_id=session_id)
    assert events_payload["events"][-2]["event_kind"] == "debug.resumed"
    assert events_payload["events"][-2]["node_id"] == "node-start"
    assert events_payload["events"][-1]["event_kind"] == "debug.completed"


def test_abort_debug_session_marks_session_aborted_and_persists_history(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))
    project_path = tmp_path / "debug-abort.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    abort_result = service.abort_debug_session(
        session_id=session_id,
        reason="user_abort",
    )

    assert abort_result["debug_session"]["session_id"] == session_id
    assert abort_result["debug_session"]["status"] == "aborted"
    assert abort_result["debug_session"]["last_control_action"] == "abort"
    assert abort_result["debug_session"]["paused_reason"] == "user_abort"

    events_payload = service.list_debug_session_events(session_id=session_id)
    assert events_payload["events"][-1]["event_kind"] == "debug.aborted"
    assert events_payload["events"][-1]["reason"] == "user_abort"
    session_payload = service.get_debug_session(session_id=session_id)
    assert session_payload["debug_keyframes"][-1]["event_kind"] == "debug.aborted"

    history_payload = service.list_debug_history_sessions()
    assert history_payload["sessions"][0]["session_id"] == session_id
    assert history_payload["sessions"][0]["status"] == "aborted"


def test_project_debug_history_retention_limit_trims_history_sessions(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))
    project_path = tmp_path / "debug-history-limit.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["debug_profile"] = {"history_retention_limit": 2}
    service.update_project_settings(project_settings=project_settings)

    session_ids: list[str] = []
    for _ in range(3):
        start_result = service.start_debug_session(graph_document_payload=None)
        session_id = start_result["debug_session"]["session_id"]
        session_ids.append(session_id)
        service.abort_debug_session(session_id=session_id, reason="user_abort")

    history_payload = service.list_debug_history_sessions()

    assert [item["session_id"] for item in history_payload["sessions"]] == session_ids[::-1][:2]


def test_workspace_state_keeps_only_recent_full_debug_sessions_without_trimming_history(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))
    project_path = tmp_path / "debug-live-state-limit.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    project_settings = service.get_project_settings_document()["project_settings"]
    project_settings["debug_profile"] = {"history_retention_limit": 4}
    service.update_project_settings(project_settings=project_settings)

    session_ids: list[str] = []
    for _ in range(4):
        started = service.start_debug_session(graph_document_payload=None)
        session_id = started["debug_session"]["session_id"]
        session_ids.append(session_id)
        service.abort_debug_session(session_id=session_id, reason="user_abort")

    persisted_state = json.loads(workspace_state_path.read_text(encoding="utf-8"))
    live_session_ids = [
        item["debug_session"]["session_id"]
        for item in persisted_state["debug_sessions"]
    ]
    history_session_ids = [
        item["session_id"]
        for item in service.list_debug_history_sessions()["sessions"]
    ]

    assert live_session_ids == session_ids[::-1][:2]
    assert history_session_ids == session_ids[::-1]
    assert service.open_debug_history_session(session_id=session_ids[0])["session"][
        "debug_session"
    ]["session_id"] == session_ids[0]


def test_aborted_debug_session_rejects_followup_control_actions(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_debug_execution_workspace_graph(start_breakpoint_before=True))
    project_path = tmp_path / "debug-abort-guard.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service.abort_debug_session(session_id=session_id, reason="user_abort")

    with pytest.raises(ValueError, match="debug session already in terminal status"):
        service.continue_debug_session(session_id=session_id)

    with pytest.raises(ValueError, match="debug session already in terminal status"):
        service.step_over_debug_session(session_id=session_id)

    with pytest.raises(ValueError, match="debug abort is not allowed for session status: aborted"):
        service.abort_debug_session(session_id=session_id, reason="user_abort")


def test_continue_debug_session_async_rejects_running_session_state() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session_async(
        graph_document_payload=None,
        settle_timeout_ms=1_000,
    )
    session_id = start_result["debug_session"]["session_id"]
    assert start_result["debug_session"]["status"] == "paused"
    session_document = service.get_debug_session(session_id=session_id)
    session_document["debug_session"] = {
        **session_document["debug_session"],
        "status": "running",
        "paused_reason": None,
    }
    service._replace_debug_session_document(session_document)  # type: ignore[attr-defined]
    service._debug_execution_threads[session_id] = _AliveThread()  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="debug continue is not allowed for session status: running"):
        service.continue_debug_session_async(session_id=session_id)


def test_step_over_debug_session_async_rejects_running_session_state() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session_async(
        graph_document_payload=None,
        settle_timeout_ms=1_000,
    )
    session_id = start_result["debug_session"]["session_id"]
    assert start_result["debug_session"]["status"] == "paused"
    session_document = service.get_debug_session(session_id=session_id)
    session_document["debug_session"] = {
        **session_document["debug_session"],
        "status": "running",
        "paused_reason": None,
    }
    service._replace_debug_session_document(session_document)  # type: ignore[attr-defined]
    service._debug_execution_threads[session_id] = _AliveThread()  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="debug step is not allowed for session status: running"):
        service.step_over_debug_session_async(session_id=session_id)


@pytest.mark.parametrize(
    ("action_name", "expected_step_mode"),
    [
        ("step_over_debug_session", "step_over"),
        ("step_into_debug_session", "step_into"),
    ],
)
def test_debug_step_actions_transition_session_to_stepping(
    action_name: str,
    expected_step_mode: str,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    action = getattr(service, action_name)
    step_result = action(session_id=session_id)

    assert step_result["debug_session"]["session_id"] == session_id
    assert step_result["debug_session"]["status"] == "paused"
    assert step_result["debug_session"]["step_mode"] == expected_step_mode
