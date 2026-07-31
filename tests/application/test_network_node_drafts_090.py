from __future__ import annotations

from weconduct.application import CompilationWorkbenchService


def _port_ids(node: dict) -> set[str]:
    return {
        str(port["port_id"])
        for port in node["ports"]
        if isinstance(port, dict) and isinstance(port.get("port_id"), str)
    }


def test_network_http_request_draft_has_context_overrides_and_response_outputs() -> None:
    draft = CompilationWorkbenchService().build_graph_node_draft(
        resource_key="network.http_request",
    )
    node = draft["node"]
    port_ids = _port_ids(node)

    assert {
        "in",
        "in:url",
        "in:headers",
        "in:auth",
        "in:tls",
        "in:proxy",
        "in:timeout",
        "out:response",
        "out:status_code",
        "out:body_ref",
    } <= port_ids
    assert node["node_config"]["context_strategy"] == "inherit"


def test_network_long_connection_and_batch_drafts_have_pull_actions_and_ordered_results() -> None:
    service = CompilationWorkbenchService()
    sse = service.build_graph_node_draft(resource_key="network.sse_connect")["node"]
    websocket = service.build_graph_node_draft(resource_key="network.websocket_connect")["node"]
    batch = service.build_graph_node_draft(resource_key="network.batch_request")["node"]

    assert {"in:connection_id", "out:event", "out:connection_id"} <= _port_ids(sse)
    assert {"in:connection_id", "in:message", "out:message", "out:connection_id"} <= _port_ids(websocket)
    assert sse["node_config"]["timeout_seconds"] is None
    assert websocket["node_config"]["timeout_seconds"] is None
    assert {"in:requests", "out:results"} <= _port_ids(batch)
    assert batch["node_config"]["max_concurrency"] == 1


def test_network_graphql_draft_has_unique_ports_and_http_response_metadata() -> None:
    node = CompilationWorkbenchService().build_graph_node_draft(
        resource_key="network.graphql_request",
    )["node"]
    port_ids = [
        str(port["port_id"])
        for port in node["ports"]
        if isinstance(port, dict) and isinstance(port.get("port_id"), str)
    ]

    assert len(port_ids) == len(set(port_ids))
    assert {
        "in:endpoint",
        "in:query",
        "out:data",
        "out:errors",
        "out:response",
        "out:status_code",
        "out:headers",
        "out:body_ref",
        "out:duration_ms",
        "out:final_url",
        "out:request_id",
        "out:transport_error",
    } <= set(port_ids)


def test_network_upload_and_download_drafts_match_runtime_output_names() -> None:
    service = CompilationWorkbenchService()
    upload = service.build_graph_node_draft(resource_key="network.upload")["node"]
    download = service.build_graph_node_draft(resource_key="network.download")["node"]

    assert {"out:uploaded_size", "out:source_checksum_sha256"} <= _port_ids(upload)
    assert "out:checksum_sha256" in _port_ids(download)


def test_python_run_draft_declares_opt_in_sensitive_input_permission() -> None:
    draft = CompilationWorkbenchService().build_graph_node_draft(
        resource_key="python.run",
    )
    node = draft["node"]

    assert node["node_config"]["allow_sensitive_values"] is False
    assert draft["parameter_schema"]["allow_sensitive_values"] == {
        "type": "boolean",
        "required": False,
        "editor_kind": "checkbox",
        "path_kind": None,
    }
