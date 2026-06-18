import pytest

from weconduct.compiler import CompilerFacade
from weconduct.compiler.errors import CompilationAbortedError
from weconduct.contracts import CompilationOptions, CompilationRequest, CompilationSource


def test_native_flow_emits_graph_model() -> None:
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id="comp-native-1",
        source=CompilationSource(
            kind="native_flow",
            entry_document="examples/native.json",
            source_text='{"nodes":[{"id":"http-1","role":"action","capability_domain":"http","action_kind":"request"}]}',
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    outcome = compiler.compile(request)

    assert outcome.graph_model is not None
    assert len(outcome.graph_model.nodes) == 1
    assert outcome.graph_model.nodes[0].lowered_kind == "execution"

    diagnostics_by_stage = {entry.stage: entry for entry in outcome.diagnostic_catalog.entries}

    assert diagnostics_by_stage["parse"].stage_extension == {
        "subject_ref": "comp-native-1",
        "action": "parsed source document",
        "source_kind": "native_flow",
        "entry_document": "examples/native.json",
        "source_ref": {
            "source_kind": "native_flow",
            "entry_document": "examples/native.json",
            "node_count": 1,
            "edge_count": 0,
        },
    }
    assert diagnostics_by_stage["validate"].stage_extension == {
        "subject_ref": "http-1",
        "action": "validated bound source",
        "rule": "source.non_empty",
        "result": "passed",
        "source_ref": {
            "source_kind": "native_flow",
            "entry_document": "examples/native.json",
            "node_id": "http-1",
            "trace_ref": "trace:http-1",
        },
    }
    assert diagnostics_by_stage["emit"].stage_extension == {
        "subject_ref": "graph:comp-native-1",
        "action": "emitted graph model",
        "graph_model_id": "graph:comp-native-1",
        "emitted_node_count": 1,
        "source_ref": {
            "source_kind": "native_flow",
            "entry_document": "examples/native.json",
        },
    }


def test_native_flow_emits_declared_edges_and_default_ports() -> None:
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id="comp-native-edges",
        source=CompilationSource(
            kind="native_flow",
            entry_document="examples/native-edges.json",
            source_text=(
                '{"nodes":['
                '{"id":"http-1","role":"action","capability_domain":"http","action_kind":"request"},'
                '{"id":"transform-1","role":"transform","capability_domain":"data","action_kind":"map"}'
                '],'
                '"edges":['
                '{"id":"edge-1","from":"http-1","to":"transform-1","relation_layer":"data"}'
                ']}'
            ),
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    outcome = compiler.compile(request)

    assert outcome.graph_model is not None
    assert len(outcome.graph_model.nodes) == 2
    assert len(outcome.graph_model.edges) == 1
    assert outcome.graph_model.nodes[0].ports[0].port_id == "in"
    assert outcome.graph_model.nodes[0].ports[1].port_id == "out"
    assert outcome.graph_model.edges[0].from_port_id == "out"
    assert outcome.graph_model.edges[0].to_port_id == "in"
    assert outcome.graph_model.edges[0].relation_layer == "data"
    assert outcome.graph_model.nodes[0].node_kind == "http.request"
    assert outcome.graph_model.nodes[0].node_config["bridge_native_flow"] == {
        "role": "action",
        "capability_domain": "http",
        "action_kind": "request",
    }


def test_empty_native_flow_raises_fatal_validation_failure() -> None:
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id="comp-native-empty",
        source=CompilationSource(
            kind="native_flow",
            entry_document="examples/empty.json",
            source_text='{"nodes":[]}',
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    with pytest.raises(CompilationAbortedError) as exc_info:
        compiler.compile(request)

    assert exc_info.value.status == "failed"
    diagnostic = exc_info.value.outcome.diagnostic_catalog.entries[1]

    assert diagnostic.category == "source.empty"
    assert diagnostic.stage_extension == {
        "subject_ref": "examples/empty.json",
        "action": "validated bound source",
        "rule": "source.non_empty",
        "result": "failed",
    }
