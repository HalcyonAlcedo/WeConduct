from __future__ import annotations

from pathlib import Path

from weconduct.application.runtime_projection import (
    project_runtime_plan_for_publication,
    project_runtime_value_for_publication,
)
from weconduct.network_runtime.resources import ResponseBodyRef


def test_runtime_value_projection_hides_response_body_and_sensitive_headers() -> None:
    projected = project_runtime_value_for_publication(
        {
            "body_ref": ResponseBodyRef(
                session_id="session-1",
                storage_kind="file",
                size_bytes=42,
                content_type="application/json",
                path=Path("C:/private/session-1/response.bin"),
            ),
            "headers": {
                "Content-Type": "application/json",
                "Set-Cookie": "session=private-cookie",
            },
        }
    )

    assert projected == {
        "body_ref": {
            "kind": "network_response_body",
            "storage_kind": "file",
            "size_bytes": 42,
            "content_type": "application/json",
        },
        "headers": {
            "Content-Type": "application/json",
            "Set-Cookie": "<redacted>",
        },
    }


def test_runtime_plan_projection_exposes_configured_field_names_without_values() -> None:
    projected = project_runtime_plan_for_publication(
        {
            "graph_model_id": "graph:workspace",
            "executable_nodes": [
                {
                    "node_id": "request-1",
                    "node_kind": "network.http_request",
                    "node_config": {
                        "url": "https://private.example.test",
                        "headers": {"Authorization": "Bearer private-token"},
                    },
                }
            ],
        }
    )

    assert projected["executable_nodes"][0]["node_config"] == {
        "configured_fields": ["headers", "url"],
        "sensitive_fields": ["headers"],
    }
