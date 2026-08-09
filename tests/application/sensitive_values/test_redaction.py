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


def test_redaction_preserves_protocol_capability_boolean_fields() -> None:
    redacted = redact_sensitive_payload(
        {
            "network": {
                "protocols": {
                    "oauth_client_credentials": True,
                    "oauth_refresh": False,
                }
            }
        }
    )

    assert redacted["network"]["protocols"] == {
        "oauth_client_credentials": True,
        "oauth_refresh": False,
    }


def test_redaction_still_hides_credentials_outside_capability_context() -> None:
    redacted = redact_sensitive_payload(
        {
            "oauth_client_credentials": "private-client-credentials",
            "network": {
                "protocols": {
                    "oauth_client_credentials": "private-client-credentials",
                }
            },
            "auth": {
                "type": "oauth_client_credentials",
                "client_secret": "private-client-secret",
            },
        }
    )

    assert redacted == {
        "oauth_client_credentials": "<redacted>",
        "network": {"protocols": {"oauth_client_credentials": "<redacted>"}},
        "auth": {
            "type": "oauth_client_credentials",
            "client_secret": "<redacted>",
        },
    }


def test_redaction_keeps_debug_variable_descriptor_structure() -> None:
    redacted = redact_sensitive_payload(
        {
            "variable_descriptors": {
                "api_key": {"name": "api_key", "sensitive": True, "value_type": "string"},
            },
            "variable_snapshot": {"api_key": "private-value"},
        },
        secret_values=["private-value"],
    )

    assert redacted["variable_descriptors"]["api_key"]["sensitive"] is True
    assert redacted["variable_snapshot"]["api_key"] == "<redacted>"


def test_redaction_uses_variable_descriptor_sensitive_marker_without_plaintext_value() -> None:
    redacted = redact_sensitive_payload(
        {
            "variable_descriptors": {
                "sid": {"name": "sid", "sensitive": True, "value_type": "string"},
                "safe": {"name": "safe", "sensitive": False, "value_type": "string"},
            },
            "variable_snapshot": {"sid": "private-session-id", "safe": "visible"},
            "variable_changes": {"sid": "rotated-session-id", "safe": "changed"},
        }
    )

    assert redacted["variable_descriptors"]["sid"]["sensitive"] is True
    assert redacted["variable_snapshot"] == {"sid": "<redacted>", "safe": "visible"}
    assert redacted["variable_changes"] == {"sid": "<redacted>", "safe": "changed"}


def test_redaction_hides_protocol_credential_aliases_in_headers_queries_and_urls() -> None:
    redacted = redact_sensitive_payload(
        {
            "auth": {"clientKey": "client-key-secret", "type": "custom"},
            "headers": {"X-Session-Id": "session-header", "Accept": "application/json"},
            "query": {"sid": "session-query", "page": "1"},
            "callback_url": "https://user:password@example.test/callback?sid=session-url&page=1",
        }
    )

    assert redacted == {
        "auth": {"clientKey": "<redacted>", "type": "custom"},
        "headers": {"X-Session-Id": "<redacted>", "Accept": "application/json"},
        "query": {"sid": "<redacted>", "page": "1"},
        "callback_url": "https://<redacted>@example.test/callback?sid=%3Credacted%3E&page=1",
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
