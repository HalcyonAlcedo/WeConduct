from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from weconduct.application.sensitive_values.models import SensitiveConsumer
from weconduct.application.sensitive_values.service import SensitiveValueService
from weconduct.packaging.msgpack_codec import packb


def test_sensitive_values_are_scoped_derived_and_revocable() -> None:
    service = SensitiveValueService()
    source = service.create(
        "runtime-secret",
        scope_id="session-1",
        source="runtime_input",
    )
    derived = service.derive("derived-secret", parents=[source])

    assert repr(source) == "SensitiveRef(<redacted>)"
    assert service.resolve(derived, consumer=SensitiveConsumer.NETWORK_RUNTIME) == "derived-secret"

    service.revoke_scope("session-1")

    with pytest.raises(KeyError):
        service.resolve(source, consumer=SensitiveConsumer.NETWORK_RUNTIME)


def test_sensitive_ref_rejects_plain_json_serialization() -> None:
    ref = SensitiveValueService().create(
        "runtime-secret",
        scope_id="session-1",
        source="runtime_input",
    )

    import json

    with pytest.raises(TypeError):
        json.dumps(ref)

    with pytest.raises(Exception):
        TypeAdapter(type(ref)).dump_json(ref)

    with pytest.raises(TypeError):
        packb(ref)
