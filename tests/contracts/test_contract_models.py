from weconduct.contracts import (
    CompilationOptions,
    CompilationRequest,
    CompilationSource,
    GraphEdge,
    GraphModel,
    GraphNode,
    GraphPort,
    GraphPosition,
    GraphViewport,
    create_empty_diagnostic_catalog,
    create_empty_graph_model,
    create_initial_summary,
)


def test_contract_factories_return_serializable_defaults() -> None:
    request = CompilationRequest(
        compilation_id="comp-1",
        source=CompilationSource(
            kind="graph_workspace",
            entry_document="graph:workspace",
            source_text='{"graph_model_id":"graph:workspace","compilation_id":null,"graph_schema_version":"graph-v1","nodes":[],"edges":[],"graph_effective_diagnostic_anchor_refs":[]}',
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    assert request.source.kind == "graph_workspace"
    assert create_initial_summary("comp-1").stage_outcomes[0].stage == "parse"
    assert create_empty_diagnostic_catalog().entries == []
    assert create_empty_graph_model("graph-1", "comp-1").nodes == []


def test_graph_contract_supports_editable_workspace_fields() -> None:
    graph = GraphModel(
        graph_model_id="graph:workspace",
        compilation_id=None,
        graph_schema_version="graph-v1",
        viewport=GraphViewport(x=12, y=24, zoom=1.25),
        nodes=[
            GraphNode(
                node_id="node-1",
                lowered_kind="execution",
                source_anchor_ref="n1",
                expansion_role="action:request",
                display_name="HTTP Request",
                node_kind="http.request",
                position=GraphPosition(x=120, y=80),
                ports=[
                    GraphPort(
                        port_id="out-main",
                        direction="output",
                        relation_layer="data",
                        semantic_slot="out.result",
                    )
                ],
                node_config={"method": "GET"},
            )
        ],
        edges=[
            GraphEdge(
                edge_id="edge-1",
                relation_layer="data",
                from_node_id="node-1",
                to_node_id="node-2",
                from_port_id="out-main",
                to_port_id="in-main",
                edge_state="draft",
            )
        ],
    )

    payload = graph.model_dump()

    assert payload["compilation_id"] is None
    assert payload["graph_schema_version"] == "graph-v1"
    assert payload["viewport"]["zoom"] == 1.25
    assert payload["nodes"][0]["display_name"] == "HTTP Request"
    assert payload["nodes"][0]["position"]["x"] == 120
    assert payload["nodes"][0]["ports"][0]["port_id"] == "out-main"
    assert payload["edges"][0]["from_port_id"] == "out-main"
    assert payload["edges"][0]["edge_state"] == "draft"


def test_graph_contract_preserves_root_metadata() -> None:
    graph = GraphModel(
        graph_model_id="graph:legacy-import",
        compilation_id="comp-legacy-root",
        graph_schema_version="graph-v1",
        root_metadata={
            "source_kind": "webcontrol_main_flow",
            "project_info": {"name": "legacy-demo"},
            "program_config": {"engine_type": "playwright"},
            "browser_config": {"headless": True},
            "global_config": {"step_delay": 0.5},
            "dialog_config": {"default_action": "accept"},
            "debug_config": {"enabled": True},
            "initial_variables": {"username": "alice"},
        },
    )

    payload = graph.model_dump()

    assert payload["root_metadata"] == {
        "source_kind": "webcontrol_main_flow",
        "project_info": {"name": "legacy-demo"},
        "program_config": {"engine_type": "playwright"},
        "browser_config": {"headless": True},
        "global_config": {"step_delay": 0.5},
        "dialog_config": {"default_action": "accept"},
        "debug_config": {"enabled": True},
        "initial_variables": {"username": "alice"},
    }


def test_compilation_source_contract_accepts_webcontrol_blueprint_kind() -> None:
    source = CompilationSource(
        kind="webcontrol_blueprint",
        entry_document="legacy/blueprints/login.json",
        source_text='{"blueprint_info":{"id":"bp-login"},"automation_steps":[]}',
    )

    assert source.kind == "webcontrol_blueprint"
