from .common import mark_stage

NATIVE_FLOW_CAPABILITY_DOMAINS = {"http", "data", "file", "os"}


class LowerStage:
    stage_name = "lower"

    def run(self, state) -> None:
        normalized = state.artifacts["normalized_source"]
        normalized_edges = state.artifacts.get("normalized_edges", [])
        raw_source = state.artifacts.get("raw_source", {})
        source_kind = raw_source.get("source_meta", {}).get("source_kind")

        lowered_execution = []
        for node in normalized:
            if source_kind == "graph_workspace":
                graph_node = dict(node["graph_node"])
                lowered_execution.append(
                    {
                        "node_id": graph_node["node_id"],
                        "lowered_kind": graph_node["lowered_kind"],
                        "source_anchor_ref": graph_node["source_anchor_ref"],
                        "expansion_role": graph_node["expansion_role"],
                        "display_name": graph_node.get("display_name"),
                        "node_kind": graph_node.get("node_kind"),
                        "position": graph_node.get("position"),
                        "ports": list(graph_node.get("ports", [])),
                        "node_config": dict(graph_node.get("node_config", {})),
                    }
                )
                continue

            capability_domain = node["classification_resolution"]["capability_domain"]
            action_name = self._resolve_action_name(node["raw_declaration"])
            top_level_role = node["classification_resolution"]["top_level_role"]
            lowered_node = {
                "node_id": node["node_id"],
                "lowered_kind": "execution",
                "source_anchor_ref": node["node_id"],
                "expansion_role": f"{top_level_role}:{action_name}",
                "node_config": {},
            }
            if source_kind in {"webcontrol_main_flow", "webcontrol_blueprint"}:
                lowered_node["node_kind"] = f"browser.{action_name}"
                lowered_node["node_config"]["legacy_step"] = dict(node.get("legacy_step", {}))
                lowered_node["node_config"]["legacy_project"] = dict(node.get("legacy_project", {}))
                if source_kind == "webcontrol_blueprint":
                    lowered_node["node_config"]["legacy_blueprint"] = dict(
                        node.get("legacy_blueprint", {})
                    )
            if capability_domain in NATIVE_FLOW_CAPABILITY_DOMAINS:
                lowered_node["node_kind"] = f"{capability_domain}.{action_name}"
                lowered_node["node_config"]["bridge_native_flow"] = {
                    "role": top_level_role,
                    "capability_domain": capability_domain,
                    "action_kind": action_name,
                }
            lowered_execution.append(lowered_node)

        lowered_edges = []
        for edge in normalized_edges:
            if source_kind == "graph_workspace":
                graph_edge = dict(edge["graph_edge"])
                lowered_edges.append(
                    {
                        "edge_id": graph_edge["edge_id"],
                        "relation_layer": graph_edge["relation_layer"],
                        "from_node_id": graph_edge["from_node_id"],
                        "to_node_id": graph_edge["to_node_id"],
                        "from_port_id": graph_edge.get("from_port_id"),
                        "to_port_id": graph_edge.get("to_port_id"),
                        "edge_state": graph_edge.get("edge_state"),
                    }
                )
                continue

            lowered_edges.append(
                {
                    "edge_id": edge["edge_id"],
                    "relation_layer": edge["relation_layer"],
                    "from_source_anchor_ref": edge["from_node_id"],
                    "to_source_anchor_ref": edge["to_node_id"],
                }
            )

        state.artifacts["lowered_execution"] = lowered_execution
        state.artifacts["lowered_edges"] = lowered_edges
        mark_stage(state, self.stage_name, "succeeded")

    def _resolve_action_name(self, raw_declaration: dict) -> str:
        return raw_declaration.get("action_kind") or raw_declaration.get("action") or "unknown"
