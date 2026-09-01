from __future__ import annotations

import json

from weconduct.application import CompilationWorkbenchService


def test_debug_worker_failure_diagnostic_redacts_network_material(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    service = CompilationWorkbenchService()
    session_id = "debug-worker-redaction"
    service._remember_debug_session(  # type: ignore[attr-defined]
        {
            "request": {},
            "debug_session": {
                "session_id": session_id,
                "status": "running",
                "started_at": "2026-08-31T00:00:00Z",
            },
            "stage_timeline": [],
            "object_index": {"graph_model_id": "graph:workspace"},
            "diagnostic_links": [],
            "debug_events": [],
            "debug_keyframes": [],
            "variable_snapshot": {},
            "runtime_preview": {},
            "runtime_preview_summary": {},
        }
    )

    service._mark_debug_worker_failed(  # type: ignore[attr-defined]
        session_id=session_id,
        error=RuntimeError(
            "request failed https://user:secret-pass@example.test/x?access_token=secret-token "
            "response_body=secret-body"
        ),
    )

    persisted = service._find_debug_session(session_id)  # type: ignore[attr-defined]
    serialized = json.dumps(persisted, ensure_ascii=False)
    assert "secret-pass" not in serialized
    assert "secret-token" not in serialized
    assert "secret-body" not in serialized
    assert "<redacted>" in persisted["diagnostic_links"][0]["message"]
