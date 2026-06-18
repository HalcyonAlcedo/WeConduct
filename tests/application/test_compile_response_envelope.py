from weconduct.application import CompilationWorkbenchService


def test_compile_source_returns_failed_envelope_for_unsupported_source_kind() -> None:
    service = CompilationWorkbenchService()

    result = service.compile_source(
        source_kind="unsupported_kind",
        entry_document="examples/unsupported.json",
        source_text="{}",
    )

    assert result["status"] == "unsupported"
    assert result["outcome"] is not None
    assert result["outcome"].graph_model is None
    assert result["outcome"].diagnostic_catalog.entries[0].category == "source.unsupported_kind"
    assert result["view"]["stage_cards"][0]["stage"] == "parse"
    assert result["view"]["stage_cards"][0]["status"] == "failed"
    assert result["view"]["diagnostic_groups"][0]["category"] == "source.unsupported_kind"
    assert result["view"]["diagnostic_summary"]["total_count"] == 1
    assert result["view"]["diagnostic_summary"]["highest_severity"] == "fatal"
    assert result["view"]["primary_diagnostic"]["category"] == "source.unsupported_kind"
    assert result["view"]["stage_overview"]["total_stage_count"] == 6
    assert result["view"]["stage_overview"]["failed_stage_count"] == 1
    assert result["view"]["stage_overview"]["succeeded_stage_count"] == 0
    assert result["view"]["stage_overview"]["terminal_stage"] == "parse"
    assert result["view"]["graph_stats"]["node_count"] == 0
    assert result["view"]["duration_ms"] is not None
    assert isinstance(result["view"]["duration_ms"], int)
    assert result["view"]["duration_ms"] >= 0
    assert result["outcome"].compilation_summary.duration_ms == result["view"]["duration_ms"]


def test_compile_source_returns_ui_facing_view_for_successful_compilation() -> None:
    service = CompilationWorkbenchService()

    result = service.compile_source(
        source_kind="native_flow",
        entry_document="examples/success.json",
        source_text='{"nodes":[{"id":"n1","role":"action","capability_domain":"http","action_kind":"request"}]}',
    )

    assert result["status"] == "succeeded"
    assert result["view"]["status"] == "succeeded"
    assert result["view"]["graph_stats"]["node_count"] == 1
    assert result["view"]["graph_stats"]["edge_count"] == 0
    assert result["view"]["stage_cards"][0]["stage"] == "parse"
    assert result["view"]["stage_cards"][-1]["stage"] == "emit"
    assert result["view"]["diagnostic_groups"][0]["stage"] == "parse"
    assert result["view"]["diagnostic_summary"]["total_count"] >= 1
    assert result["view"]["diagnostic_summary"]["highest_severity"] == "info"
    assert result["view"]["primary_diagnostic"]["stage"] == "parse"
    assert result["view"]["stage_overview"]["total_stage_count"] == 6
    assert result["view"]["stage_overview"]["succeeded_stage_count"] == 6
    assert result["view"]["stage_overview"]["failed_stage_count"] == 0
    assert result["view"]["stage_overview"]["terminal_stage"] == "emit"
    assert result["view"]["duration_ms"] is not None
    assert isinstance(result["view"]["duration_ms"], int)
    assert result["view"]["duration_ms"] >= 0
    assert result["outcome"].compilation_summary.duration_ms == result["view"]["duration_ms"]


def test_compile_source_returns_failed_envelope_for_invalid_native_flow_source_text() -> None:
    service = CompilationWorkbenchService()

    result = service.compile_source(
        source_kind="native_flow",
        entry_document="examples/invalid-native-flow.json",
        source_text="{not-json",
    )

    assert result["status"] == "failed"
    assert result["view"]["status"] == "failed"
    assert result["view"]["stage_cards"][0]["stage"] == "parse"
    assert result["view"]["stage_cards"][0]["status"] == "failed"
    assert result["view"]["diagnostic_groups"][0]["category"] == "source.parse_error"
    assert result["view"]["diagnostic_summary"]["highest_severity"] == "fatal"
    assert result["view"]["primary_diagnostic"]["category"] == "source.parse_error"
    assert result["view"]["stage_overview"]["failed_stage_count"] == 1
    assert result["view"]["stage_overview"]["terminal_stage"] == "parse"
    assert result["outcome"].graph_model is None
    assert result["outcome"].diagnostic_catalog.entries[0].category == "source.parse_error"
    assert result["view"]["duration_ms"] is not None
    assert isinstance(result["view"]["duration_ms"], int)
    assert result["view"]["duration_ms"] >= 0
    assert result["outcome"].compilation_summary.duration_ms == result["view"]["duration_ms"]


def test_compile_source_accepts_webcontrol_blueprint_source_kind() -> None:
    service = CompilationWorkbenchService()

    result = service.compile_source(
        source_kind="webcontrol_blueprint",
        entry_document="legacy/blueprints/login.json",
        source_text=(
            '{'
            '"blueprint_info":{"id":"bp-login"},'
            '"input_schema":{"username":{"type":"string"}},'
            '"output_schema":{"logged_in":{"type":"boolean"}},'
            '"automation_steps":[{"step_id":"step-1","action":"open_url"}]'
            '}'
        ),
    )

    assert result["status"] == "succeeded"
    assert result["request"].source.kind == "webcontrol_blueprint"
    assert result["outcome"].graph_model is not None
    assert result["outcome"].graph_model.root_metadata["source_kind"] == "webcontrol_blueprint"


def test_compile_graph_document_returns_ui_facing_view_for_invalid_graph() -> None:
    service = CompilationWorkbenchService()

    result = service.compile_graph_document(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [],
            "edges": [
                {
                    "edge_id": "edge-1",
                    "relation_layer": "data",
                    "from_node_id": "missing-a",
                    "to_node_id": "missing-b",
                    "from_port_id": "out",
                    "to_port_id": "in",
                }
            ],
            "graph_effective_diagnostic_anchor_refs": [],
        }
    )

    assert result["status"] == "failed"
    assert result["view"]["status"] == "failed"
    assert result["view"]["diagnostic_summary"]["highest_severity"] == "fatal"
    assert result["view"]["primary_diagnostic"]["category"].startswith("graph.edge.")
    assert result["view"]["duration_ms"] is not None
    assert isinstance(result["view"]["duration_ms"], int)
    assert result["view"]["duration_ms"] >= 0
    assert result["outcome"].compilation_summary.duration_ms == result["view"]["duration_ms"]


def test_compile_graph_document_returns_failed_envelope_for_empty_graph_workspace() -> None:
    service = CompilationWorkbenchService()

    result = service.compile_graph_document(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
    )

    assert result["status"] == "failed"
    assert result["view"]["status"] == "failed"
    assert result["view"]["stage_overview"]["terminal_stage"] == "validate"
    assert result["view"]["primary_diagnostic"]["category"] == "source.empty"
    assert result["request"]["source_kind"] == "graph_workspace"
    assert result["request"]["source"]["kind"] == "graph_workspace"
    assert result["view"]["duration_ms"] is not None
    assert isinstance(result["view"]["duration_ms"], int)
    assert result["view"]["duration_ms"] >= 0
    assert result["outcome"].compilation_summary.duration_ms == result["view"]["duration_ms"]
