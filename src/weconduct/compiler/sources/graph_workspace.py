import json

from weconduct.contracts import GraphModel


def parse_graph_workspace(source_text: str) -> GraphModel:
    payload = json.loads(source_text)
    return GraphModel.model_validate(payload)
