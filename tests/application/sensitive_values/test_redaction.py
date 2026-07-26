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
        "authorization": "<redacted>",
        "nested": ["<sensitive-ref>", "safe"],
    }


def test_redaction_hides_sensitive_response_headers_and_cookie_values() -> None:
    redacted = redact_sensitive_payload(
        {
            "headers": {
                "Content-Type": "application/json",
                "Set-Cookie": "session=private-cookie",
            },
            "cookies": {"session": "private-cookie"},
        }
    )

    assert redacted == {
        "headers": {
            "Content-Type": "application/json",
            "Set-Cookie": "<redacted>",
        },
        "cookies": {"session": "<redacted>"},
    }


def test_redaction_hides_camel_case_keys_and_credential_fields() -> None:
    redacted = redact_sensitive_payload(
        {
            "apiKey": "api-key-secret",
            "access_key": "access-key-secret",
            "credential": "credential-secret",
            "displayName": "safe",
        }
    )

    assert redacted == {
        "apiKey": "<redacted>",
        "access_key": "<redacted>",
        "credential": "<redacted>",
        "displayName": "safe",
    }


def test_redaction_hides_sensitive_query_values_in_runtime_urls() -> None:
    redacted = redact_sensitive_payload(
        {
            "final_url": "https://example.test/callback?access_token=private&safe=value",
            "message": "access_token=private",
        }
    )

    assert redacted == {
        "final_url": "https://example.test/callback?access_token=%3Credacted%3E&safe=value",
        "message": "access_token=private",
    }
