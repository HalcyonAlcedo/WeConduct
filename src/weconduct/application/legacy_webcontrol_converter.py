from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from weconduct.builtin_components import get_graph_node_draft_definition
from weconduct.builtin_components.registry import build_builtin_resource_registry
from weconduct.compiler import CompilerFacade
from weconduct.compiler.sources.legacy_webcontrol import (
    build_legacy_webcontrol_blueprint_custom_node_graph_seed,
)
from weconduct.contracts import (
    CompilationRequest,
    CompilationSource,
    GraphEdge,
    GraphModel,
    GraphNode,
    GraphPosition,
    GraphViewport,
)


@dataclass(slots=True)
class LegacyBlueprintConversionResult:
    source_path: Path
    resource_record: dict


@dataclass(slots=True)
class LegacyWebControlConversionResult:
    source_path: Path
    source_kind: str
    project_name: str
    graph_model: GraphModel
    legacy_root_metadata: dict
    blueprint_results: list[LegacyBlueprintConversionResult]
    warnings: list[dict]


@dataclass(slots=True)
class _LegacyStepMapping:
    resource_key: str
    config_builder: callable


LEGACY_ACTION_MAPPINGS: dict[str, _LegacyStepMapping] = {
    "open_url": _LegacyStepMapping("browser.navigate", lambda step: {"url": step.get("url", "")}),
    "navigate": _LegacyStepMapping("browser.navigate", lambda step: {"url": step.get("url", "")}),
    "click_element": _LegacyStepMapping("browser.click", lambda step: {"selector": step.get("selector", "")}),
    "click": _LegacyStepMapping("browser.click", lambda step: {"selector": step.get("selector", "")}),
    "input_text": _LegacyStepMapping(
        "browser.fill",
        lambda step: {"selector": step.get("selector", ""), "value": step.get("text", "")},
    ),
    "fill": _LegacyStepMapping(
        "browser.fill",
        lambda step: {"selector": step.get("selector", ""), "value": step.get("value", "")},
    ),
    "select_option": _LegacyStepMapping(
        "browser.select_option",
        lambda step: {"selector": step.get("selector", ""), "value": step.get("value", "")},
    ),
    "hover": _LegacyStepMapping("browser.hover", lambda step: {"selector": step.get("selector", "")}),
    "wait_for_element": _LegacyStepMapping(
        "browser.wait_for_element",
        lambda step: {
            "selector": step.get("selector", ""),
            "timeout": _coerce_int(step.get("timeout"), default=10000),
        },
    ),
    "wait_for_navigation": _LegacyStepMapping(
        "browser.wait_for_navigation",
        lambda step: {
            "url_pattern": step.get("url_pattern", step.get("url", "")),
            "timeout": _coerce_int(step.get("timeout"), default=15000),
        },
    ),
    "wait_for_timeout": _LegacyStepMapping(
        "browser.wait_for_timeout",
        lambda step: {
            "timeout": _coerce_int(
                step.get("timeout", step.get("milliseconds")),
                default=0,
            )
        },
    ),
    "screenshot": _LegacyStepMapping(
        "browser.screenshot",
        lambda step: {"path": step.get("filename", step.get("path", ""))},
    ),
    "get_text": _LegacyStepMapping(
        "data.get_text",
        lambda step: {
            "selector": step.get("selector", ""),
            "variable_name": _first_non_blank(
                step.get("variable_name"),
                step.get("target_variable"),
                step.get("name"),
            ),
        },
    ),
    "get_attribute": _LegacyStepMapping(
        "data.get_attribute",
        lambda step: {
            "selector": step.get("selector", ""),
            "attribute": step.get("attribute", ""),
            "variable_name": _first_non_blank(
                step.get("variable_name"),
                step.get("target_variable"),
                step.get("name"),
            ),
        },
    ),
    "get_value": _LegacyStepMapping(
        "data.get_value",
        lambda step: {
            "selector": step.get("selector", ""),
            "variable_name": _first_non_blank(
                step.get("variable_name"),
                step.get("target_variable"),
                step.get("name"),
            ),
        },
    ),
    "get_element_count": _LegacyStepMapping(
        "data.get_element_count",
        lambda step: {
            "selector": step.get("selector", ""),
            "variable_name": _first_non_blank(
                step.get("variable_name"),
                step.get("target_variable"),
                step.get("name"),
            ),
        },
    ),
    "extract_web_table": _LegacyStepMapping(
        "browser.extract_web_table",
        lambda step: {
            "selector": step.get("selector", ""),
            "variable_name": _first_non_blank(
                step.get("variable_name"),
                step.get("target_variable"),
            ),
        },
    ),
    "extract_web_table_to_excel": _LegacyStepMapping(
        "browser.extract_web_table_to_excel",
        lambda step: {
            "selector": step.get("selector", ""),
            "path": step.get("file_path", step.get("path", "")),
            "sheet_name": step.get("sheet_name", "Sheet1"),
        },
    ),
    "recognize_captcha": _LegacyStepMapping(
        "browser.recognize_captcha",
        lambda step: {
            "selector": step.get("selector", ""),
            "target_variable": _first_non_blank(
                step.get("target_variable"),
                step.get("variable_name"),
                step.get("name"),
            ),
            "model_name": step.get("model_name", step.get("model", "")),
            "runtime_root": step.get("runtime_root", ""),
        },
    ),
    "set_variable": _LegacyStepMapping(
        "data.set_variable",
        lambda step: {
            "name": _first_non_blank(step.get("variable_name"), step.get("name")),
            "value": step.get("value"),
        },
    ),
    "increment_variable": _LegacyStepMapping(
        "data.increment_variable",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable_name"), step.get("name")),
            "amount": _coerce_numeric(step.get("amount"), default=1),
        },
    ),
    "decrement_variable": _LegacyStepMapping(
        "data.decrement_variable",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable_name"), step.get("name")),
            "amount": _coerce_numeric(step.get("amount"), default=1),
        },
    ),
    "calculate_expression": _LegacyStepMapping(
        "data.evaluate_expression",
        lambda step: {
            "expression": step.get("expression", ""),
            "variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("variable_name"),
                step.get("name"),
            ),
        },
    ),
    "evaluate_expression": _LegacyStepMapping(
        "data.evaluate_expression",
        lambda step: {
            "expression": step.get("expression", ""),
            "variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("variable_name"),
                step.get("name"),
            ),
        },
    ),
    "regex_replace": _LegacyStepMapping(
        "data.regex_replace",
        lambda step: {
            "text": _build_regex_replace_text(step),
            "pattern": step.get("pattern", ""),
            "replacement": step.get("replacement", ""),
            "variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("variable_name"),
                step.get("name"),
            ),
        },
    ),
    "create_list": _LegacyStepMapping(
        "data.create_list",
        lambda step: {
            "variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("variable_name"),
                step.get("name"),
            ),
            "items": step.get("items", []),
        },
    ),
    "list_append": _LegacyStepMapping(
        "data.list_append",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
            "value": step.get("value"),
        },
    ),
    "list_extend": _LegacyStepMapping(
        "data.list_extend",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
            "items": step.get("items", []),
        },
    ),
    "list_insert": _LegacyStepMapping(
        "data.list_insert",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
            "index": _coerce_int(step.get("index"), default=0),
            "value": step.get("value"),
        },
    ),
    "list_get": _LegacyStepMapping(
        "data.list_get",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
            "index": _coerce_int(step.get("index"), default=0),
            "output_variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("output_variable_name"),
            ),
        },
    ),
    "list_set": _LegacyStepMapping(
        "data.list_set",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
            "index": _coerce_int(step.get("index"), default=0),
            "value": step.get("value"),
        },
    ),
    "list_index": _LegacyStepMapping(
        "data.list_index",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
            "value": step.get("value"),
            "output_variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("output_variable_name"),
            ),
        },
    ),
    "list_slice": _LegacyStepMapping(
        "data.list_slice",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
            "start": _coerce_int(step.get("start"), default=0),
            "end": _coerce_int(step.get("end"), default=0) if step.get("end") is not None else None,
            "output_variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("output_variable_name"),
            ),
        },
    ),
    "list_length": _LegacyStepMapping(
        "data.list_length",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
            "output_variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("output_variable_name"),
            ),
        },
    ),
    "list_sort": _LegacyStepMapping(
        "data.list_sort",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
        },
    ),
    "list_reverse": _LegacyStepMapping(
        "data.list_reverse",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
        },
    ),
    "list_remove": _LegacyStepMapping(
        "data.list_remove",
        lambda step: {
            "variable_name": _first_non_blank(step.get("variable"), step.get("variable_name"), step.get("name")),
            "value": step.get("value"),
            **({"index": _coerce_int(step.get("index"), default=0)} if step.get("index") is not None else {}),
        },
    ),
    "foreach": _LegacyStepMapping(
        "control.foreach",
        lambda step: {
            "variable": _first_non_blank(step.get("variable"), step.get("items_variable")),
            "item_var": _first_non_blank(step.get("item_var"), "item"),
            "index_var": _first_non_blank(step.get("index_var"), "index"),
        },
    ),
    "end_foreach": _LegacyStepMapping("control.end_foreach", lambda step: {}),
    "write_excel_file": _LegacyStepMapping(
        "excel.write_file",
        lambda step: {
            "path": step.get("file_path", step.get("path", "")),
            "sheet_name": step.get("sheet_name", "Sheet1"),
            "rows": step.get("rows", []),
        },
    ),
    "write_excel_row": _LegacyStepMapping(
        "excel.write_row",
        lambda step: {
            "path": step.get("file_path", step.get("path", "")),
            "sheet_name": step.get("sheet_name", "Sheet1"),
            "row_index": _coerce_int(step.get("row_index"), default=1),
            "data": step.get("data", []),
        },
    ),
    "write_excel_cell": _LegacyStepMapping(
        "excel.write_cell",
        lambda step: {
            "path": step.get("file_path", step.get("path", "")),
            "sheet_name": step.get("sheet_name", "Sheet1"),
            "cell": _build_excel_cell_ref(step),
            "value": step.get("value"),
        },
    ),
    "read_excel_cell": _LegacyStepMapping(
        "excel.read_cell",
        lambda step: {
            "path": step.get("file_path", step.get("path", "")),
            "sheet_name": step.get("sheet_name", "Sheet1"),
            "cell": _build_excel_cell_ref(step),
            "variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("variable_name"),
                step.get("name"),
            ),
        },
    ),
    "read_excel_row": _LegacyStepMapping(
        "excel.read_row",
        lambda step: {
            "path": step.get("file_path", step.get("path", "")),
            "sheet_name": step.get("sheet_name", "Sheet1"),
            "row_index": _coerce_int(step.get("row_index"), default=1),
            "variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("variable_name"),
                step.get("name"),
            ),
        },
    ),
    "read_excel_table": _LegacyStepMapping(
        "excel.read_table",
        lambda step: {
            "path": step.get("file_path", step.get("path", "")),
            "sheet_name": step.get("sheet_name", "Sheet1"),
            "has_header": True,
            "variable_name": _first_non_blank(
                step.get("target_variable"),
                step.get("variable_name"),
                step.get("name"),
            ),
        },
    ),
    "handle_dialogs": _LegacyStepMapping(
        "dialog.set_agent_config",
        lambda step: {
            "default_action": _normalize_dialog_action(step.get("action_param", step.get("action"))),
            "prompt_text": step.get("prompt_text", ""),
        },
    ),
    "call_blueprint": _LegacyStepMapping(
        "call_blueprint",
        lambda step: {
            "blueprint_id": step.get("blueprint_id", ""),
            "inputs": step.get("inputs", {}),
            "outputs": step.get("outputs", {}),
        },
    ),
}


def parse_legacy_webcontrol_document(source_path: str | Path) -> tuple[dict, str, str]:
    resolved_path = Path(source_path).expanduser().resolve()
    if not resolved_path.exists():
        raise ValueError(f"legacy source file not found: {resolved_path}")
    if not resolved_path.is_file():
        raise ValueError(f"legacy source path must point to a file: {resolved_path}")
    source_text = resolved_path.read_text(encoding="utf-8")
    payload = _load_legacy_payload(source_text=source_text, source_path=resolved_path)
    source_kind = detect_legacy_webcontrol_source_kind(payload)
    return payload, source_text, source_kind


def detect_legacy_webcontrol_source_kind(payload: dict) -> str:
    automation_steps = payload.get("automation_steps")
    if not isinstance(automation_steps, list):
        raise ValueError("legacy source missing required list: automation_steps")
    if isinstance(payload.get("blueprint_info"), dict):
        return "webcontrol_blueprint"
    return "webcontrol_main_flow"


def convert_legacy_webcontrol_project(
    *,
    source_path: str | Path,
    blueprint_paths: list[str | Path] | None = None,
    blueprint_directory: str | Path | None = None,
    preserve_legacy_metadata: bool = True,
) -> LegacyWebControlConversionResult:
    payload, _source_text, source_kind = parse_legacy_webcontrol_document(source_path)
    if source_kind != "webcontrol_main_flow":
        raise ValueError(f"legacy source is not a WebControl main flow: {Path(source_path).resolve()}")

    graph_model = _build_editable_graph_workspace_from_legacy_main_flow(
        payload=payload,
        source_path=Path(source_path).resolve(),
        preserve_legacy_metadata=preserve_legacy_metadata,
    )

    discovered_blueprint_paths = _discover_blueprint_paths(
        blueprint_paths=blueprint_paths,
        blueprint_directory=blueprint_directory,
    )
    blueprint_results: list[LegacyBlueprintConversionResult] = []
    warnings: list[dict] = []
    seen_resource_ids: set[str] = set()
    seen_blueprint_aliases: set[str] = set()
    for blueprint_path in discovered_blueprint_paths:
        try:
            result = convert_legacy_webcontrol_blueprint(
                blueprint_path,
                preserve_legacy_metadata=preserve_legacy_metadata,
            )
        except ValueError as exc:
            warnings.append(
                {
                    "code": "blueprint.import_failed",
                    "message": str(exc),
                    "path": str(Path(blueprint_path).resolve()),
                }
            )
            continue
        resource_id = result.resource_record["resource_id"]
        aliases = set(result.resource_record.get("compatibility_aliases", []))
        if resource_id in seen_resource_ids or aliases.intersection(seen_blueprint_aliases):
            warnings.append(
                {
                    "code": "blueprint.duplicate_skipped",
                    "message": f"duplicate blueprint skipped: {resource_id}",
                    "path": str(Path(blueprint_path).resolve()),
                }
            )
            continue
        seen_resource_ids.add(resource_id)
        seen_blueprint_aliases.update(aliases)
        blueprint_results.append(result)

    project_info = payload.get("project_info")
    project_name = "Imported WebControl Project"
    if isinstance(project_info, dict):
        raw_name = project_info.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            project_name = raw_name.strip()
    return LegacyWebControlConversionResult(
        source_path=Path(source_path).resolve(),
        source_kind=source_kind,
        project_name=project_name,
        graph_model=graph_model,
        legacy_root_metadata=dict(graph_model.root_metadata or {}),
        blueprint_results=blueprint_results,
        warnings=warnings,
    )


def convert_legacy_webcontrol_blueprint(
    blueprint_path: str | Path,
    *,
    preserve_legacy_metadata: bool = True,
) -> LegacyBlueprintConversionResult:
    payload, source_text, source_kind = parse_legacy_webcontrol_document(blueprint_path)
    resolved_path = Path(blueprint_path).expanduser().resolve()
    if source_kind != "webcontrol_blueprint":
        raise ValueError(f"legacy blueprint file is not a blueprint: {resolved_path}")
    normalized_source_text = _normalize_legacy_source_text_for_compiler(
        payload=payload,
        source_text=source_text,
    )
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id=f"legacy-blueprint-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        source=CompilationSource(
            kind="webcontrol_blueprint",
            entry_document=str(resolved_path),
            source_text=normalized_source_text,
        ),
    )
    outcome = compiler.compile(request)
    if outcome.graph_model is None:
        raise ValueError(f"legacy WebControl blueprint compile produced no graph: {resolved_path}")
    graph_model = outcome.graph_model.model_copy(deep=True)
    if preserve_legacy_metadata:
        root_metadata = dict(graph_model.root_metadata or {})
        root_metadata["legacy_webcontrol_blueprint_source"] = {
            "source_path": str(resolved_path),
            "source_kind": "webcontrol_blueprint",
            "converted_at": datetime.now(timezone.utc).isoformat(),
        }
        graph_model.root_metadata = root_metadata
    resource_seed = build_legacy_webcontrol_blueprint_custom_node_graph_seed(
        normalized_source_text,
        fallback_name=resolved_path.stem,
    )
    resource_record = {
        **resource_seed,
        "source_graph_document_id": graph_model.graph_model_id,
        "source_graph_document_save_revision": 1,
        "source_graph_document": graph_model.model_dump(mode="json"),
    }
    return LegacyBlueprintConversionResult(
        source_path=resolved_path,
        resource_record=resource_record,
    )


def build_conversion_report(
    *,
    conversion: LegacyWebControlConversionResult,
    output_project_path: Path,
    report_path: Path | None,
    errors: list[dict] | None = None,
) -> dict:
    return {
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(conversion.source_path),
        "source_kind": conversion.source_kind,
        "output_project_path": str(output_project_path.resolve()),
        "report_path": str(report_path.resolve()) if report_path is not None else None,
        "project_name": conversion.project_name,
        "main_graph_node_count": len(conversion.graph_model.nodes),
        "main_graph_edge_count": len(conversion.graph_model.edges),
        "imported_blueprint_count": len(conversion.blueprint_results),
        "generated_resource_count": len(conversion.blueprint_results),
        "resource_ids": [
            item.resource_record["resource_id"] for item in conversion.blueprint_results
        ],
        "warnings": list(conversion.warnings),
        "errors": list(errors or []),
    }


def _build_editable_graph_workspace_from_legacy_main_flow(
    *,
    payload: dict,
    source_path: Path,
    preserve_legacy_metadata: bool,
) -> GraphModel:
    resource_registry = {
        item["resource_key"]: item
        for item in build_builtin_resource_registry()
        if isinstance(item.get("resource_key"), str)
    }
    automation_steps = payload.get("automation_steps", [])
    if not isinstance(automation_steps, list):
        raise ValueError("legacy source missing required list: automation_steps")

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    flow_start = _build_graph_node_from_resource(
        resource_key="flow.start",
        node_id="node-start",
        resource_registry=resource_registry,
        position={"x": -320.0, "y": 0.0},
    )
    flow_start.node_config["initial_variables"] = dict(payload.get("initial_variables", {}))
    flow_start.node_config["browser_config"] = _build_flow_start_browser_config(payload)
    nodes.append(flow_start)
    previous_node_id = flow_start.node_id
    previous_control_port_id = "out"

    for index, raw_step in enumerate(automation_steps):
        if not isinstance(raw_step, dict):
            raise ValueError(f"legacy automation step must be an object: step[{index}]")
        action = raw_step.get("action")
        if not isinstance(action, str) or not action.strip():
            raise ValueError(f"legacy automation step missing action: step[{index}]")
        mapping = LEGACY_ACTION_MAPPINGS.get(action.strip())
        if mapping is None:
            raise ValueError(f"legacy action is not supported for editable conversion: {action.strip()}")

        step_id = _normalize_legacy_step_id(raw_step, index=index)
        node_id = f"ln:{step_id}"
        node = _build_graph_node_from_resource(
            resource_key=mapping.resource_key,
            node_id=node_id,
            resource_registry=resource_registry,
            position={"x": float(index * 280), "y": 0.0},
        )
        node.node_config.update(mapping.config_builder(raw_step))
        if preserve_legacy_metadata:
            node.node_config["legacy_webcontrol_step"] = {
                "source_path": str(source_path),
                "step_index": index,
                "step_id": step_id,
                "action": action.strip(),
                "raw_declaration": deepcopy(raw_step),
            }
        nodes.append(node)

        target_control_port_id = _find_first_control_input_port_id(node)
        edges.append(
            GraphEdge(
                edge_id=f"legacy-edge-{index + 1}",
                relation_layer="control",
                from_node_id=previous_node_id,
                to_node_id=node.node_id,
                from_port_id=previous_control_port_id,
                to_port_id=target_control_port_id,
                edge_state="draft",
            )
        )
        previous_node_id = node.node_id
        previous_control_port_id = _find_first_control_output_port_id(node)

    root_metadata = {
        "source_kind": "webcontrol_main_flow",
        "project_info": dict(payload.get("project_info", {})),
        "program_config": dict(payload.get("program_config", {})),
        "browser_config": dict(payload.get("browser_config", {})),
        "global_config": dict(payload.get("global_config", {})),
        "dialog_config": dict(payload.get("dialog_config", {})),
        "debug_config": dict(payload.get("debug_config", {})),
        "initial_variables": dict(payload.get("initial_variables", {})),
    }
    if preserve_legacy_metadata:
        root_metadata["legacy_webcontrol_source"] = {
            "source_path": str(source_path),
            "source_kind": "webcontrol_main_flow",
            "converted_at": datetime.now(timezone.utc).isoformat(),
        }

    return GraphModel(
        graph_model_id="graph:workspace",
        compilation_id=None,
        graph_schema_version="graph-v1",
        nodes=nodes,
        edges=edges,
        viewport=GraphViewport(x=0.0, y=0.0, zoom=1.0),
        root_metadata=root_metadata,
        graph_effective_diagnostic_anchor_refs=[],
    )


def _build_graph_node_from_resource(
    *,
    resource_key: str,
    node_id: str,
    resource_registry: dict[str, dict],
    position: dict[str, float],
) -> GraphNode:
    draft_definition = get_graph_node_draft_definition(resource_key)
    if draft_definition is None:
        raise ValueError(f"missing graph node draft definition for resource: {resource_key}")
    resource = resource_registry.get(resource_key)
    display_name = resource.get("display_name_i18n", {}).get("zh-CN") if isinstance(resource, dict) else None
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = resource.get("display_name") if isinstance(resource, dict) else resource_key
    return GraphNode.model_validate(
        {
            "node_id": node_id,
            "lowered_kind": draft_definition["lowered_kind"],
            "source_anchor_ref": f"n-{node_id}",
            "expansion_role": draft_definition["expansion_role"],
            "display_name": display_name.strip() if isinstance(display_name, str) else resource_key,
            "node_kind": resource_key,
            "position": GraphPosition(x=float(position["x"]), y=float(position["y"])).model_dump(),
            "ports": deepcopy(draft_definition.get("ports", [])),
            "node_config": deepcopy(draft_definition.get("node_config", {})),
        }
    )


def _build_flow_start_browser_config(payload: dict) -> dict:
    browser_config = dict(payload.get("browser_config", {}))
    program_config = dict(payload.get("program_config", {}))
    headless = browser_config.get("headless")
    if headless is None:
        headless = program_config.get("headless")
    slow_mo = browser_config.get("slow_mo_ms")
    if slow_mo is None:
        slow_mo = browser_config.get("slow_mo")
    if slow_mo is None:
        slow_mo = program_config.get("slow_mo_ms")
    if slow_mo is None:
        slow_mo = program_config.get("slow_mo")
    return {
        "headless": bool(headless) if headless is not None else True,
        "slow_mo_ms": _coerce_int(slow_mo, default=0),
    }


def _normalize_legacy_step_id(step: dict, *, index: int) -> str:
    for key in ("step_id", "id", "step"):
        value = step.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return f"legacy-step-{index + 1}"


def _find_first_control_input_port_id(node: GraphNode) -> str | None:
    for port in node.ports:
        if port.direction == "input" and port.relation_layer == "control":
            return port.port_id
    return None


def _find_first_control_output_port_id(node: GraphNode) -> str | None:
    for port in node.ports:
        if port.direction == "output" and port.relation_layer == "control":
            return port.port_id
    return None


def _load_legacy_payload(*, source_text: str, source_path: Path) -> dict:
    suffix = source_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            payload = yaml.safe_load(source_text)
        except yaml.YAMLError as exc:
            raise ValueError(f"legacy source file must be valid YAML: {source_path}") from exc
    else:
        try:
            payload = json.loads(source_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"legacy source file must be valid JSON: {source_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"legacy source file must be a mapping object: {source_path}")
    return payload


def _normalize_legacy_source_text_for_compiler(*, payload: dict, source_text: str) -> str:
    stripped = source_text.lstrip()
    if stripped.startswith("{"):
        return source_text
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _discover_blueprint_paths(
    *,
    blueprint_paths: list[str | Path] | None,
    blueprint_directory: str | Path | None,
) -> list[Path]:
    items: list[Path] = []
    seen: set[str] = set()
    for raw_path in blueprint_paths or []:
        resolved = Path(raw_path).expanduser().resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        items.append(resolved)
    if blueprint_directory is not None:
        directory = Path(blueprint_directory).expanduser().resolve()
        if not directory.exists():
            raise ValueError(f"legacy blueprint directory not found: {directory}")
        if not directory.is_dir():
            raise ValueError(f"legacy blueprint directory must be a folder: {directory}")
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".json", ".yaml", ".yml"}:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            items.append(path.resolve())
    return items


def _coerce_int(value, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(float(stripped))
        except ValueError:
            return default
    return default


def _coerce_numeric(value, *, default: int | float) -> int | float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            parsed = float(stripped)
        except ValueError:
            return default
        return int(parsed) if parsed.is_integer() else parsed
    return default


def _first_non_blank(*values) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_dialog_action(value) -> str:
    normalized = str(value).strip().lower() if value is not None else ""
    if normalized in {"dismiss", "reject", "cancel"}:
        return "dismiss"
    return "accept"


def _build_excel_cell_ref(step: dict) -> str:
    cell = step.get("cell")
    if isinstance(cell, str) and cell.strip():
        return cell.strip()
    row_index = step.get("row_index")
    column_index = step.get("column_index")
    if row_index is None or column_index is None:
        return ""
    row = _coerce_int(row_index, default=0)
    column = _coerce_int(column_index, default=0)
    if row < 1 or column < 1:
        return ""
    return f"{_excel_column_name(column)}{row}"


def _excel_column_name(index: int) -> str:
    label = []
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        label.append(chr(ord("A") + remainder))
    return "".join(reversed(label))


def _build_regex_replace_text(step: dict):
    source_variable = step.get("source_variable")
    if isinstance(source_variable, str) and source_variable.strip():
        return f"${{{source_variable.strip()}}}"
    return step.get("text", "")
