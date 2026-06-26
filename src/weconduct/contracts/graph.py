from typing import Any, Literal

from pydantic import BaseModel, Field


class GraphPosition(BaseModel):
    x: float
    y: float


class GraphViewport(BaseModel):
    x: float
    y: float
    zoom: float


class GraphPort(BaseModel):
    port_id: str
    direction: Literal["input", "output"]
    relation_layer: Literal["control", "data", "observe"]
    semantic_slot: str
    display_name: str | None = None
    max_connections: int | None = None


class GraphNode(BaseModel):
    node_id: str
    lowered_kind: Literal["execution", "control", "observe", "bridge"]
    source_anchor_ref: str
    expansion_role: str
    display_name: str | None = None
    node_kind: str | None = None
    position: GraphPosition | None = None
    ports: list[GraphPort] = Field(default_factory=list)
    node_config: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    edge_id: str
    relation_layer: Literal["control", "data", "observe"]
    from_node_id: str
    to_node_id: str
    from_port_id: str | None = None
    to_port_id: str | None = None
    edge_state: str | None = None


class GraphModel(BaseModel):
    graph_model_id: str
    compilation_id: str | None
    graph_schema_version: str = "graph-v1"
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    viewport: GraphViewport | None = None
    root_metadata: dict[str, Any] = Field(default_factory=dict)
    graph_effective_diagnostic_anchor_refs: list[str] = Field(default_factory=list)


def create_empty_graph_model(graph_model_id: str, compilation_id: str | None) -> GraphModel:
    return GraphModel(
        graph_model_id=graph_model_id,
        compilation_id=compilation_id,
        root_metadata={
            "graph_compatibility": {
                "graph_data_version": "0.6.2",
                "built_with_app_version": "0.7.0",
                "minimum_loader_app_version": "0.5.2",
                "last_upgraded_by_app_version": "0.7.0",
                "upgrade_history": [],
            }
        },
    )
