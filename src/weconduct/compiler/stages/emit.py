from weconduct.contracts import GraphEdge, GraphModel, GraphNode, GraphPort, GraphPosition, GraphViewport
from weconduct.compiler.services import StableIdentityService

from .common import append_stage_diagnostic, mark_stage


class EmitStage:
    stage_name = "emit"

    def run(self, state) -> None:
        lowered = state.artifacts["lowered_execution"]
        lowered_edges = state.artifacts.get("lowered_edges", [])
        raw_source = state.artifacts.get("raw_source", {})
        source_kind = raw_source.get("source_meta", {}).get("source_kind")
        root_metadata = dict(raw_source.get("root_metadata", {}))
        stable_identity_service = StableIdentityService()

        if source_kind == "graph_workspace":
            graph_model_id = raw_source.get("graph_model_id", state.request.source.entry_document)
            emitted_nodes = [
                GraphNode(
                    node_id=node["node_id"],
                    lowered_kind=node["lowered_kind"],
                    source_anchor_ref=node["source_anchor_ref"],
                    expansion_role=node["expansion_role"],
                    display_name=node.get("display_name"),
                    node_kind=node.get("node_kind"),
                    position=(
                        GraphPosition.model_validate(node["position"])
                        if node.get("position") is not None
                        else None
                    ),
                    ports=[
                        GraphPort.model_validate(port)
                        for port in node.get("ports", [])
                    ],
                    node_config=node.get("node_config", {}),
                )
                for node in lowered
            ]
            state.artifacts["graph_model"] = GraphModel(
                graph_model_id=graph_model_id,
                compilation_id=state.request.compilation_id,
                graph_schema_version="graph-v1",
                nodes=emitted_nodes,
                edges=[
                    GraphEdge(
                        edge_id=edge["edge_id"],
                        relation_layer=edge["relation_layer"],
                        from_node_id=edge["from_node_id"],
                        to_node_id=edge["to_node_id"],
                        from_port_id=edge.get("from_port_id"),
                        to_port_id=edge.get("to_port_id"),
                        edge_state=edge.get("edge_state"),
                    )
                    for edge in lowered_edges
                ],
                viewport=(
                    GraphViewport.model_validate(raw_source["viewport"])
                    if raw_source.get("viewport") is not None
                    else None
                ),
                root_metadata=root_metadata,
                graph_effective_diagnostic_anchor_refs=[
                    item.diagnostic_id for item in state.diagnostics
                ],
            )
            append_stage_diagnostic(
                state,
                diagnostic_id=f"{state.request.compilation_id}:emit",
                stage=self.stage_name,
                severity="info",
                category="emit.completed",
                message="emitted graph model",
                stage_extension={
                    "subject_ref": graph_model_id,
                    "action": "emitted graph model",
                    "graph_model_id": graph_model_id,
                    "emitted_node_count": len(lowered),
                    "source_ref": {
                        "source_kind": source_kind,
                        "entry_document": state.request.source.entry_document,
                        "graph_model_id": graph_model_id,
                    },
                },
                object_ref=graph_model_id,
            )
            mark_stage(state, self.stage_name, "succeeded")
            return

        graph_model_id = f"graph:{state.request.compilation_id}"
        emitted_nodes = [
            GraphNode(
                node_id=stable_identity_service.create_lowered_node_id(
                    source_anchor_ref=node["source_anchor_ref"],
                    expansion_role=node["expansion_role"],
                    lowered_kind=node["lowered_kind"],
                ),
                lowered_kind=node["lowered_kind"],
                source_anchor_ref=node["source_anchor_ref"],
                expansion_role=node["expansion_role"],
                display_name=node["expansion_role"],
                node_kind=node.get("node_kind") or node["expansion_role"],
                ports=[
                    GraphPort(
                        port_id="in",
                        direction="input",
                        relation_layer="data",
                        semantic_slot="in.default",
                    ),
                    GraphPort(
                        port_id="out",
                        direction="output",
                        relation_layer="data",
                        semantic_slot="out.default",
                    ),
                ],
                node_config=node.get("node_config", {}),
            )
            for node in lowered
        ]
        node_id_by_source_anchor_ref = {
            node.source_anchor_ref: node.node_id for node in emitted_nodes
        }
        state.artifacts["graph_model"] = GraphModel(
            graph_model_id=graph_model_id,
            compilation_id=state.request.compilation_id,
            nodes=emitted_nodes,
            edges=[
                GraphEdge(
                    edge_id=edge["edge_id"],
                    relation_layer=edge["relation_layer"],
                    from_node_id=node_id_by_source_anchor_ref[edge["from_source_anchor_ref"]],
                    to_node_id=node_id_by_source_anchor_ref[edge["to_source_anchor_ref"]],
                    from_port_id="out",
                    to_port_id="in",
                )
                for edge in lowered_edges
                if edge["from_source_anchor_ref"] in node_id_by_source_anchor_ref
                and edge["to_source_anchor_ref"] in node_id_by_source_anchor_ref
            ],
            root_metadata=root_metadata,
            graph_effective_diagnostic_anchor_refs=[
                item.diagnostic_id for item in state.diagnostics
            ],
        )
        append_stage_diagnostic(
            state,
            diagnostic_id=f"{state.request.compilation_id}:emit",
            stage=self.stage_name,
            severity="info",
            category="emit.completed",
            message="emitted graph model",
            stage_extension={
                "subject_ref": graph_model_id,
                "action": "emitted graph model",
                "graph_model_id": graph_model_id,
                "emitted_node_count": len(lowered),
                "source_ref": {
                    "source_kind": source_kind,
                    "entry_document": state.request.source.entry_document,
                },
            },
            object_ref=graph_model_id,
        )
        mark_stage(state, self.stage_name, "succeeded")
