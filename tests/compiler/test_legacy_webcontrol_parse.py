from weconduct.compiler import CompilerFacade
from weconduct.contracts import CompilationOptions, CompilationRequest, CompilationSource


def test_legacy_webcontrol_steps_map_to_graph_nodes() -> None:
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id="comp-legacy-1",
        source=CompilationSource(
            kind="webcontrol_main_flow",
            entry_document="legacy/main.json",
            source_text=(
                '{"project_info":{"name":"demo"},'
                '"automation_steps":[{"step_id":"step-1","action":"open_url"},{"step_id":"step-2","action":"click_element"}]}'
            ),
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    outcome = compiler.compile(request)

    assert outcome.graph_model is not None
    assert len(outcome.graph_model.nodes) == 2
    assert len(outcome.graph_model.edges) == 1
    assert outcome.graph_model.edges[0].relation_layer == "control"
    assert outcome.graph_model.edges[0].from_node_id == outcome.graph_model.nodes[0].node_id
    assert outcome.graph_model.edges[0].to_node_id == outcome.graph_model.nodes[1].node_id
    assert outcome.graph_model.edges[0].from_port_id == "out"
    assert outcome.graph_model.edges[0].to_port_id == "in"
    assert outcome.graph_model.nodes[0].node_kind == "browser.open_url"
    assert outcome.graph_model.nodes[0].node_config["legacy_step"] == {
        "step_id": "step-1",
        "action": "open_url",
    }
    assert outcome.graph_model.nodes[1].node_config["legacy_step"] == {
        "step_id": "step-2",
        "action": "click_element",
    }

    diagnostics_by_stage = {entry.stage: entry for entry in outcome.diagnostic_catalog.entries}

    assert diagnostics_by_stage["parse"].stage_extension == {
        "subject_ref": "comp-legacy-1",
        "action": "parsed source document",
        "source_kind": "webcontrol_main_flow",
        "entry_document": "legacy/main.json",
        "legacy_project_name": "demo",
        "source_ref": {
            "source_kind": "webcontrol_main_flow",
            "entry_document": "legacy/main.json",
            "legacy_project_name": "demo",
            "node_count": 2,
            "edge_count": 1,
        },
    }
    assert diagnostics_by_stage["validate"].stage_extension == {
        "subject_ref": "step-1",
        "action": "validated bound source",
        "rule": "source.non_empty",
        "result": "passed",
        "source_ref": {
            "source_kind": "webcontrol_main_flow",
            "entry_document": "legacy/main.json",
            "node_id": "step-1",
            "trace_ref": "trace:step-1",
        },
    }
    assert diagnostics_by_stage["emit"].stage_extension == {
        "subject_ref": "graph:comp-legacy-1",
        "action": "emitted graph model",
        "graph_model_id": "graph:comp-legacy-1",
        "emitted_node_count": 2,
        "source_ref": {
            "source_kind": "webcontrol_main_flow",
            "entry_document": "legacy/main.json",
        },
    }


def test_legacy_webcontrol_preserves_step_arguments_and_project_metadata() -> None:
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id="comp-legacy-args",
        source=CompilationSource(
            kind="webcontrol_main_flow",
            entry_document="legacy/with-args.json",
            source_text=(
                '{"project_info":{"name":"demo-args","environment":"staging"},'
                '"automation_steps":['
                '{"step_id":"step-1","action":"open_url","url":"https://example.com"},'
                '{"step_id":"step-2","action":"input_text","selector":"#user","text":"alice"}'
                ']}'
            ),
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    outcome = compiler.compile(request)

    assert outcome.graph_model is not None
    assert outcome.graph_model.nodes[0].node_kind == "browser.open_url"
    assert outcome.graph_model.nodes[0].node_config["legacy_project"] == {
        "name": "demo-args",
        "environment": "staging",
    }
    assert outcome.graph_model.nodes[0].node_config["legacy_step"]["url"] == "https://example.com"
    assert outcome.graph_model.nodes[1].node_kind == "browser.input_text"
    assert outcome.graph_model.nodes[1].node_config["legacy_step"]["selector"] == "#user"
    assert outcome.graph_model.nodes[1].node_config["legacy_step"]["text"] == "alice"


def test_legacy_webcontrol_preserves_root_level_configs_in_graph_model() -> None:
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id="comp-legacy-root-meta",
        source=CompilationSource(
            kind="webcontrol_main_flow",
            entry_document="legacy/root-meta.json",
            source_text=(
                '{'
                '"project_info":{"name":"demo-root","version":"1.0.0"},'
                '"program_config":{"engine_type":"playwright"},'
                '"browser_config":{"headless":true,"timeout":30000},'
                '"global_config":{"step_delay":0.5},'
                '"dialog_config":{"default_action":"accept"},'
                '"debug_config":{"enabled":true},'
                '"initial_variables":{"username":"alice"},'
                '"automation_steps":[{"step_id":"step-1","action":"open_url","url":"https://example.com"}]'
                '}'
            ),
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    outcome = compiler.compile(request)

    assert outcome.graph_model is not None
    assert outcome.graph_model.root_metadata == {
        "source_kind": "webcontrol_main_flow",
        "project_info": {"name": "demo-root", "version": "1.0.0"},
        "program_config": {"engine_type": "playwright"},
        "browser_config": {"headless": True, "timeout": 30000},
        "global_config": {"step_delay": 0.5},
        "dialog_config": {"default_action": "accept"},
        "debug_config": {"enabled": True},
        "initial_variables": {"username": "alice"},
    }


def test_legacy_webcontrol_blueprint_maps_to_graph_nodes_and_root_metadata() -> None:
    compiler = CompilerFacade()
    request = CompilationRequest(
        compilation_id="comp-legacy-blueprint",
        source=CompilationSource(
            kind="webcontrol_blueprint",
            entry_document="legacy/blueprints/login.json",
            source_text=(
                '{'
                '"blueprint_info":{"id":"bp-login","name":"Login Blueprint"},'
                '"input_schema":{"username":{"type":"string"}},'
                '"output_schema":{"logged_in":{"type":"boolean"}},'
                '"automation_steps":['
                '{"step_id":"step-1","action":"open_url","url":"https://example.com/login"},'
                '{"step_id":"step-2","action":"input_text","selector":"#user","text":"${username}"}'
                ']}'
            ),
        ),
        options=CompilationOptions(stop_on_fatal=True),
    )

    outcome = compiler.compile(request)

    assert outcome.graph_model is not None
    assert len(outcome.graph_model.nodes) == 2
    assert len(outcome.graph_model.edges) == 1
    assert outcome.graph_model.root_metadata == {
        "source_kind": "webcontrol_blueprint",
        "blueprint_info": {"id": "bp-login", "name": "Login Blueprint"},
        "input_schema": {"username": {"type": "string"}},
        "output_schema": {"logged_in": {"type": "boolean"}},
    }
    diagnostics_by_stage = {entry.stage: entry for entry in outcome.diagnostic_catalog.entries}
    assert diagnostics_by_stage["parse"].stage_extension == {
        "subject_ref": "comp-legacy-blueprint",
        "action": "parsed source document",
        "source_kind": "webcontrol_blueprint",
        "entry_document": "legacy/blueprints/login.json",
        "legacy_blueprint_id": "bp-login",
        "source_ref": {
            "source_kind": "webcontrol_blueprint",
            "entry_document": "legacy/blueprints/login.json",
            "legacy_blueprint_id": "bp-login",
            "node_count": 2,
            "edge_count": 1,
        },
    }
