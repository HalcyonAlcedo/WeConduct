import json
from typing import Literal

from pydantic import BaseModel, Field


class NativeFlowNode(BaseModel):
    id: str
    role: Literal["action", "transform", "condition"]
    capability_domain: Literal["http", "data", "file", "os", "browser", "excel", "python"]
    action_kind: str


class NativeFlowEdge(BaseModel):
    id: str
    from_node_id: str = Field(alias="from")
    to_node_id: str = Field(alias="to")
    relation_layer: Literal["control", "data", "observe"] = "data"


class NativeFlowDocument(BaseModel):
    nodes: list[NativeFlowNode]
    edges: list[NativeFlowEdge] = Field(default_factory=list)


def parse_native_flow(source_text: str) -> NativeFlowDocument:
    payload = json.loads(source_text)
    return NativeFlowDocument.model_validate(payload)
