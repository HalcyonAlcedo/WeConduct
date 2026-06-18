from weconduct.compiler import CompilerFacade
from weconduct.contracts import CompilationOptions, CompilationRequest, CompilationSource


def test_compiler_runs_all_six_stages_in_order() -> None:
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id="comp-1",
        source=CompilationSource(
            kind="native_flow",
            entry_document="examples/minimal.json",
            source_text='{"nodes":[{"id":"n1","role":"action","capability_domain":"http","action_kind":"request"}]}',
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    outcome = compiler.compile(request)

    assert [item.stage for item in outcome.compilation_summary.stage_outcomes] == [
        "parse",
        "bind",
        "validate",
        "normalize",
        "lower",
        "emit",
    ]
