import pytest

from weconduct.compiler import CompilerFacade
from weconduct.compiler.errors import CompilationAbortedError
from weconduct.contracts import CompilationOptions, CompilationRequest, CompilationSource


def test_graph_workspace_compilation_preserves_graph_identity_ports_edges_and_position() -> None:
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id="comp-graph-1",
        source=CompilationSource(
            kind="graph_workspace",
            entry_document="graph:workspace",
            source_text=(
                '{"graph_model_id":"graph:workspace","compilation_id":null,'
                '"graph_schema_version":"graph-v1","nodes":['
                '{"node_id":"node-1","lowered_kind":"execution","source_anchor_ref":"n1",'
                '"expansion_role":"action:request","display_name":"HTTP Request",'
                '"node_kind":"http.request","position":{"x":120,"y":80},"ports":['
                '{"port_id":"out-main","direction":"output","relation_layer":"data",'
                '"semantic_slot":"out.result"}],"node_config":{"method":"GET"}},'
                '{"node_id":"node-2","lowered_kind":"execution","source_anchor_ref":"n2",'
                '"expansion_role":"transform:map","display_name":"Map Result",'
                '"node_kind":"data.map","position":{"x":360,"y":80},"ports":['
                '{"port_id":"in-main","direction":"input","relation_layer":"data",'
                '"semantic_slot":"in.default"}],"node_config":{"mode":"map"}}],'
                '"edges":[{"edge_id":"edge-1","relation_layer":"data","from_node_id":"node-1",'
                '"to_node_id":"node-2","from_port_id":"out-main","to_port_id":"in-main",'
                '"edge_state":"draft"}],"viewport":{"x":0,"y":0,"zoom":1.1},'
                '"graph_effective_diagnostic_anchor_refs":[]}'
            ),
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    outcome = compiler.compile(request)

    assert outcome.graph_model is not None
    assert outcome.graph_model.graph_model_id == "graph:workspace"
    assert outcome.graph_model.viewport is not None
    assert outcome.graph_model.viewport.zoom == 1.1
    assert outcome.graph_model.nodes[0].node_id == "node-1"
    assert outcome.graph_model.nodes[0].position is not None
    assert outcome.graph_model.nodes[0].position.x == 120
    assert outcome.graph_model.nodes[0].ports[0].port_id == "out-main"
    assert outcome.graph_model.nodes[0].node_config == {"method": "GET"}
    assert outcome.graph_model.edges[0].edge_id == "edge-1"
    assert outcome.graph_model.edges[0].from_node_id == "node-1"
    assert outcome.graph_model.edges[0].to_node_id == "node-2"
    assert outcome.graph_model.edges[0].from_port_id == "out-main"
    assert outcome.graph_model.edges[0].to_port_id == "in-main"
    diagnostics_by_stage = {entry.stage: entry for entry in outcome.diagnostic_catalog.entries}
    assert diagnostics_by_stage["parse"].stage_extension == {
        "subject_ref": "comp-graph-1",
        "action": "parsed source document",
        "source_kind": "graph_workspace",
        "entry_document": "graph:workspace",
        "source_ref": {
            "source_kind": "graph_workspace",
            "entry_document": "graph:workspace",
            "graph_model_id": "graph:workspace",
            "node_count": 2,
            "edge_count": 1,
        },
    }
    assert diagnostics_by_stage["emit"].stage_extension == {
        "subject_ref": "graph:workspace",
        "action": "emitted graph model",
        "graph_model_id": "graph:workspace",
        "emitted_node_count": 2,
        "source_ref": {
            "source_kind": "graph_workspace",
            "entry_document": "graph:workspace",
            "graph_model_id": "graph:workspace",
        },
    }


def test_empty_graph_workspace_raises_fatal_validation_failure() -> None:
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id="comp-graph-empty",
        source=CompilationSource(
            kind="graph_workspace",
            entry_document="graph:workspace",
            source_text=(
                '{"graph_model_id":"graph:workspace","compilation_id":null,'
                '"graph_schema_version":"graph-v1","nodes":[],"edges":[],'
                '"graph_effective_diagnostic_anchor_refs":[]}'
            ),
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    with pytest.raises(CompilationAbortedError) as exc_info:
        compiler.compile(request)

    assert exc_info.value.status == "failed"
    diagnostic = exc_info.value.outcome.diagnostic_catalog.entries[1]
    assert diagnostic.category == "source.empty"
    assert diagnostic.stage_extension == {
        "subject_ref": "graph:workspace",
        "action": "validated bound source",
        "rule": "source.non_empty",
        "result": "failed",
    }
