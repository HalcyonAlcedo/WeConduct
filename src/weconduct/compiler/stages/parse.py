from weconduct.compiler.sources.graph_workspace import parse_graph_workspace
from weconduct.compiler.sources.legacy_webcontrol import (
    parse_legacy_webcontrol_blueprint,
    parse_legacy_webcontrol_main_flow,
)
from weconduct.compiler.sources.native_flow import parse_native_flow

from .common import append_stage_diagnostic, mark_stage


class ParseStage:
    stage_name = "parse"

    def run(self, state) -> None:
        if state.request.source.kind == "graph_workspace":
            graph_model = parse_graph_workspace(state.request.source.source_text)
            state.artifacts["raw_source"] = {
                "source_meta": {
                    "source_kind": "graph_workspace",
                    "entry_document": state.request.source.entry_document,
                    "graph_model_id": graph_model.graph_model_id,
                    "node_count": len(graph_model.nodes),
                    "edge_count": len(graph_model.edges),
                },
                "graph_model_id": graph_model.graph_model_id,
                "viewport": graph_model.viewport.model_dump() if graph_model.viewport else None,
                "root_metadata": dict(graph_model.root_metadata),
                "graph_effective_diagnostic_anchor_refs": list(
                    graph_model.graph_effective_diagnostic_anchor_refs
                ),
                "node_candidates": [
                    {
                        "node_id": node.node_id,
                        "raw_declaration": node.model_dump(),
                        "raw_classification_hints": {
                            "role": self._resolve_graph_role(node),
                            "capability_domain": self._resolve_graph_capability_domain(node),
                        },
                        "trace_ref": f"graph-node:{node.node_id}",
                    }
                    for node in graph_model.nodes
                ],
                "edge_candidates": [
                    {
                        "edge_id": edge.edge_id,
                        "from_node_id": edge.from_node_id,
                        "to_node_id": edge.to_node_id,
                        "relation_layer": edge.relation_layer,
                        "from_port_id": edge.from_port_id,
                        "to_port_id": edge.to_port_id,
                        "edge_state": edge.edge_state,
                    }
                    for edge in graph_model.edges
                ],
            }
            append_stage_diagnostic(
                state,
                diagnostic_id=f"{state.request.compilation_id}:parse",
                stage=self.stage_name,
                severity="info",
                category="parse.completed",
                message="parsed source document",
                stage_extension={
                    "subject_ref": state.request.compilation_id,
                    "action": "parsed source document",
                    "source_kind": "graph_workspace",
                    "entry_document": state.request.source.entry_document,
                    "source_ref": {
                        "source_kind": "graph_workspace",
                        "entry_document": state.request.source.entry_document,
                        "graph_model_id": graph_model.graph_model_id,
                        "node_count": len(graph_model.nodes),
                        "edge_count": len(graph_model.edges),
                    },
                },
                object_ref=state.request.source.entry_document,
            )
            mark_stage(state, self.stage_name, "succeeded")
            return

        if state.request.source.kind == "webcontrol_main_flow":
            document = parse_legacy_webcontrol_main_flow(state.request.source.source_text)
            root_metadata = document.build_root_metadata()
            state.artifacts["raw_source"] = {
                "source_meta": {
                    "source_kind": "webcontrol_main_flow",
                    "entry_document": state.request.source.entry_document,
                    "legacy_project_name": document.project_info.get("name"),
                    "node_count": len(document.automation_steps),
                    "edge_count": max(0, len(document.automation_steps) - 1),
                },
                "project_info": dict(document.project_info),
                "root_metadata": root_metadata,
                "node_candidates": [
                    {
                        "node_id": step.step_id or f"legacy-step-{index + 1}",
                        "raw_declaration": step.model_dump(),
                        "raw_classification_hints": {
                            "role": "action",
                            "capability_domain": "browser",
                        },
                        "trace_ref": f'trace:{step.step_id or index + 1}',
                    }
                    for index, step in enumerate(document.automation_steps)
                ],
                "edge_candidates": [
                    {
                        "edge_id": f"legacy-edge-{index + 1}",
                        "from_node_id": (
                            document.automation_steps[index].step_id or f"legacy-step-{index + 1}"
                        ),
                        "to_node_id": (
                            document.automation_steps[index + 1].step_id
                            or f"legacy-step-{index + 2}"
                        ),
                        "relation_layer": "control",
                    }
                    for index in range(max(0, len(document.automation_steps) - 1))
                ],
            }
            append_stage_diagnostic(
                state,
                diagnostic_id=f"{state.request.compilation_id}:parse",
                stage=self.stage_name,
                severity="info",
                category="parse.completed",
                message="parsed source document",
                stage_extension={
                    "subject_ref": state.request.compilation_id,
                    "action": "parsed source document",
                    "source_kind": "webcontrol_main_flow",
                    "entry_document": state.request.source.entry_document,
                    "legacy_project_name": document.project_info.get("name"),
                    "source_ref": {
                        "source_kind": "webcontrol_main_flow",
                        "entry_document": state.request.source.entry_document,
                        "legacy_project_name": document.project_info.get("name"),
                        "node_count": len(document.automation_steps),
                        "edge_count": max(0, len(document.automation_steps) - 1),
                    },
                },
                object_ref=state.request.source.entry_document,
            )
            mark_stage(state, self.stage_name, "succeeded")
            return

        if state.request.source.kind == "webcontrol_blueprint":
            document = parse_legacy_webcontrol_blueprint(state.request.source.source_text)
            root_metadata = document.build_root_metadata()
            state.artifacts["raw_source"] = {
                "source_meta": {
                    "source_kind": "webcontrol_blueprint",
                    "entry_document": state.request.source.entry_document,
                    "legacy_blueprint_id": document.blueprint_info.get("id"),
                    "node_count": len(document.automation_steps),
                    "edge_count": max(0, len(document.automation_steps) - 1),
                },
                "blueprint_info": dict(document.blueprint_info),
                "input_schema": dict(document.input_schema),
                "output_schema": dict(document.output_schema),
                "root_metadata": root_metadata,
                "node_candidates": [
                    {
                        "node_id": step.step_id or f"legacy-step-{index + 1}",
                        "raw_declaration": step.model_dump(),
                        "raw_classification_hints": {
                            "role": "action",
                            "capability_domain": "browser",
                        },
                        "trace_ref": f'trace:{step.step_id or index + 1}',
                    }
                    for index, step in enumerate(document.automation_steps)
                ],
                "edge_candidates": [
                    {
                        "edge_id": f"legacy-edge-{index + 1}",
                        "from_node_id": (
                            document.automation_steps[index].step_id or f"legacy-step-{index + 1}"
                        ),
                        "to_node_id": (
                            document.automation_steps[index + 1].step_id
                            or f"legacy-step-{index + 2}"
                        ),
                        "relation_layer": "control",
                    }
                    for index in range(max(0, len(document.automation_steps) - 1))
                ],
            }
            append_stage_diagnostic(
                state,
                diagnostic_id=f"{state.request.compilation_id}:parse",
                stage=self.stage_name,
                severity="info",
                category="parse.completed",
                message="parsed source document",
                stage_extension={
                    "subject_ref": state.request.compilation_id,
                    "action": "parsed source document",
                    "source_kind": "webcontrol_blueprint",
                    "entry_document": state.request.source.entry_document,
                    "legacy_blueprint_id": document.blueprint_info.get("id"),
                    "source_ref": {
                        "source_kind": "webcontrol_blueprint",
                        "entry_document": state.request.source.entry_document,
                        "legacy_blueprint_id": document.blueprint_info.get("id"),
                        "node_count": len(document.automation_steps),
                        "edge_count": max(0, len(document.automation_steps) - 1),
                    },
                },
                object_ref=state.request.source.entry_document,
            )
            mark_stage(state, self.stage_name, "succeeded")
            return

        if state.request.source.kind != "native_flow":
            raise ValueError(f"unsupported source kind: {state.request.source.kind}")

        document = parse_native_flow(state.request.source.source_text)
        state.artifacts["raw_source"] = {
            "source_meta": {
                "source_kind": state.request.source.kind,
                "entry_document": state.request.source.entry_document,
                "node_count": len(document.nodes),
                "edge_count": len(document.edges),
            },
            "node_candidates": [
                {
                    "node_id": node.id,
                    "raw_declaration": node.model_dump(),
                    "raw_classification_hints": {
                        "role": node.role,
                        "capability_domain": node.capability_domain,
                    },
                    "trace_ref": f"trace:{node.id}",
                }
                for node in document.nodes
            ],
            "edge_candidates": [
                {
                    "edge_id": edge.id,
                    "from_node_id": edge.from_node_id,
                    "to_node_id": edge.to_node_id,
                    "relation_layer": edge.relation_layer,
                }
                for edge in document.edges
            ],
        }
        append_stage_diagnostic(
            state,
            diagnostic_id=f"{state.request.compilation_id}:parse",
            stage=self.stage_name,
            severity="info",
            category="parse.completed",
            message="parsed source document",
            stage_extension={
                "subject_ref": state.request.compilation_id,
                "action": "parsed source document",
                "source_kind": state.request.source.kind,
                "entry_document": state.request.source.entry_document,
                "source_ref": {
                    "source_kind": state.request.source.kind,
                    "entry_document": state.request.source.entry_document,
                    "node_count": len(document.nodes),
                    "edge_count": len(document.edges),
                },
            },
            object_ref=state.request.source.entry_document,
        )
        mark_stage(state, self.stage_name, "succeeded")

    def _resolve_graph_role(self, node) -> str:
        expansion_role = getattr(node, "expansion_role", "")
        if isinstance(expansion_role, str) and ":" in expansion_role:
            role = expansion_role.split(":", 1)[0]
            if role in {"action", "transform", "condition"}:
                return role
        return {
            "execution": "action",
            "observe": "transform",
            "control": "condition",
            "bridge": "transform",
        }.get(getattr(node, "lowered_kind", "execution"), "action")

    def _resolve_graph_capability_domain(self, node) -> str:
        node_kind = getattr(node, "node_kind", None)
        if isinstance(node_kind, str) and "." in node_kind:
            return node_kind.split(".", 1)[0]
        node_config = getattr(node, "node_config", {})
        if isinstance(node_config, dict):
            bridge_meta = node_config.get("bridge_native_flow")
            if isinstance(bridge_meta, dict):
                capability_domain = bridge_meta.get("capability_domain")
                if isinstance(capability_domain, str) and capability_domain.strip():
                    return capability_domain
        return "graph"
