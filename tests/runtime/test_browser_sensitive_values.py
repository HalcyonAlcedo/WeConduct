from __future__ import annotations

from weconduct.application.sensitive_values.models import SensitiveRef
from weconduct.application.sensitive_values.service import SensitiveValueService
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


class _FakeLocator:
    def __init__(self) -> None:
        self.filled_values: list[str] = []

    def fill(self, value: str) -> None:
        self.filled_values.append(value)


class _FakePage:
    url = "https://example.test/login"

    def __init__(self, locator: _FakeLocator) -> None:
        self._locator = locator

    def locator(self, selector: str) -> _FakeLocator:
        assert selector == "#username"
        return self._locator


def test_browser_fill_resolves_sensitive_reference_only_at_playwright_consumer() -> None:
    sensitive_values = SensitiveValueService()
    username_ref = sensitive_values.create(
        "alice@example.test",
        scope_id="session-browser-fill",
        source="encrypted_parameter",
    )
    locator = _FakeLocator()
    context = RuntimeContext(
        variables={"username": username_ref},
        browser_runtime={"page": _FakePage(locator)},
        flow_runtime={"sensitive_value_service": sensitive_values},
    )

    result = RuntimeExecutorRegistry()._execute_browser_fill(
        {
            "node_id": "fill-username",
            "node_config": {"selector": "#username", "value": "${username}"},
        },
        context,
    )

    assert locator.filled_values == ["alice@example.test"]
    assert isinstance(result["value"], SensitiveRef)
    assert "alice@example.test" not in repr(result)
