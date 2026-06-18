from weconduct.compiler import CompilerFacade
from weconduct.contracts import CompilationOptions, CompilationRequest, CompilationSource


def test_lowered_node_id_is_stable_across_identical_compilations() -> None:
    compiler = CompilerFacade()

    source = CompilationSource(
        kind="native_flow",
        entry_document="examples/stable.json",
        source_text='{"nodes":[{"id":"n1","role":"action","capability_domain":"http","action_kind":"request"}]}',
    )

    result_a = compiler.compile(
        CompilationRequest(compilation_id="comp-a", source=source, options=CompilationOptions())
    )
    result_b = compiler.compile(
        CompilationRequest(compilation_id="comp-b", source=source, options=CompilationOptions())
    )

    assert result_a.graph_model is not None
    assert result_b.graph_model is not None
    assert result_a.graph_model.nodes[0].node_id == result_b.graph_model.nodes[0].node_id
