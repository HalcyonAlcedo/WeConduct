from .common import mark_stage


class NormalizeStage:
    stage_name = "normalize"

    def run(self, state) -> None:
        raw_source = state.artifacts.get("raw_source", {})
        source_kind = raw_source.get("source_meta", {}).get("source_kind")

        normalized_source = []
        for node in state.artifacts.get("validated_source", []):
            normalized_node = dict(node)
            if source_kind == "graph_workspace":
                normalized_node["graph_node"] = dict(node["graph_node"])
            normalized_source.append(normalized_node)

        normalized_edges = []
        for edge in state.artifacts.get("validated_edges", []):
            normalized_edge = dict(edge)
            if source_kind == "graph_workspace":
                normalized_edge["graph_edge"] = dict(edge["graph_edge"])
            normalized_edges.append(normalized_edge)

        state.artifacts["normalized_source"] = normalized_source
        state.artifacts["normalized_edges"] = normalized_edges
        mark_stage(state, self.stage_name, "succeeded")
