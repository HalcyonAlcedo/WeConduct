from .common import mark_stage


class BindStage:
    stage_name = "bind"

    def run(self, state) -> None:
        raw = state.artifacts["raw_source"]
        source_kind = raw.get("source_meta", {}).get("source_kind")

        bound_source = []
        for node in raw["node_candidates"]:
            bound_node = {
                **node,
                "classification_resolution": {
                    "top_level_role": node["raw_classification_hints"]["role"],
                    "capability_domain": node["raw_classification_hints"]["capability_domain"],
                },
            }
            if source_kind == "graph_workspace":
                bound_node["graph_node"] = node["raw_declaration"]
            if source_kind in {"webcontrol_main_flow", "webcontrol_blueprint"}:
                bound_node["legacy_step"] = dict(node["raw_declaration"])
                bound_node["legacy_project"] = dict(raw.get("project_info", {}))
                if source_kind == "webcontrol_blueprint":
                    bound_node["legacy_blueprint"] = dict(raw.get("blueprint_info", {}))
            bound_source.append(bound_node)

        bound_edges = []
        for edge in raw.get("edge_candidates", []):
            bound_edge = dict(edge)
            if source_kind == "graph_workspace":
                bound_edge["graph_edge"] = dict(edge)
            bound_edges.append(bound_edge)

        state.artifacts["bound_source"] = bound_source
        state.artifacts["bound_edges"] = bound_edges
        mark_stage(state, self.stage_name, "succeeded")
