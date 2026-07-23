from __future__ import annotations

from weconduct.application.sensitive_values.redaction import redact_sensitive_payload
from weconduct.application.sensitive_values.service import SensitiveValueService


def test_redaction_removes_plaintext_and_sensitive_refs_from_nested_payloads() -> None:
    service = SensitiveValueService()
    ref = service.create("test-secret", scope_id="session-1", source="runtime_input")

    redacted = redact_sensitive_payload(
        {"authorization": "Bearer test-secret", "nested": [ref, "safe"]},
        secret_values=["test-secret"],
    )

    assert redacted == {
        "authorization": "Bearer <redacted>",
        "nested": ["<sensitive-ref>", "safe"],
    }
