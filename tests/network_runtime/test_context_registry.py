from __future__ import annotations

import pytest

from weconduct.network_runtime.context_registry import (
    NetworkContextRegistry,
    UnknownNetworkContextError,
)
from weconduct.runtime.execution_context import ExecutionTokenContext


def test_context_registry_applies_inherit_new_anonymous_fork_switch_and_reset() -> None:
    registry = NetworkContextRegistry(
        platform_defaults={"headers": {"Accept": "application/json"}, "timeout_seconds": 15.0}
    )
    session_id = "session-1"
    root = registry.create(session_id, headers={"X-Trace": "root"}, cookies={"sid": "secret"})

    inherited = registry.apply_strategy(session_id, root, strategy="inherit")
    independent = registry.apply_strategy(
        session_id,
        root,
        strategy="new",
        overrides={"headers": {"X-Trace": "new"}},
    )
    anonymous = registry.apply_strategy(session_id, root, strategy="anonymous")
    forked = registry.apply_strategy(session_id, root, strategy="fork")
    forked_snapshot = registry.snapshot(session_id, forked)
    switched = registry.apply_strategy(
        session_id,
        root,
        strategy="switch",
        switch_context_id=forked.network_context_id,
    )
    reset = registry.apply_strategy(session_id, forked, strategy="reset")

    assert inherited == root
    assert independent.network_context_id != root.network_context_id
    assert registry.snapshot(session_id, independent).headers == {
        "Accept": "application/json",
        "X-Trace": "new",
    }
    assert registry.snapshot(session_id, anonymous).cookies == {}
    assert registry.snapshot(session_id, anonymous).headers == {"Accept": "application/json"}
    assert forked_snapshot.cookies == {"sid": "secret"}
    assert switched == forked
    assert reset.network_context_id == forked.network_context_id
    assert reset.network_context_epoch == forked.network_context_epoch + 1
    assert registry.snapshot(session_id, reset).cookies == {}
    assert registry.snapshot(session_id, reset).headers == {"Accept": "application/json"}


def test_context_registry_fork_is_isolated_from_later_parent_updates() -> None:
    registry = NetworkContextRegistry()
    session_id = "session-1"
    root = registry.create(session_id, headers={"X-Request": "parent"})
    forked = registry.apply_strategy(session_id, root, strategy="fork")

    updated_root = registry.apply_overrides(
        session_id,
        root,
        {"headers": {"X-Request": "updated", "X-Parent": "yes"}},
    )

    assert updated_root.network_context_epoch == root.network_context_epoch + 1
    assert registry.snapshot(session_id, updated_root).headers == {
        "X-Request": "updated",
        "X-Parent": "yes",
    }
    assert registry.snapshot(session_id, forked).headers == {"X-Request": "parent"}


def test_context_registry_rejects_switch_to_another_session_and_cleans_up_session() -> None:
    registry = NetworkContextRegistry()
    session_one_context = registry.create("session-1")
    session_two_context = registry.create("session-2")

    with pytest.raises(UnknownNetworkContextError):
        registry.apply_strategy(
            "session-1",
            session_one_context,
            strategy="switch",
            switch_context_id=session_two_context.network_context_id,
        )

    registry.clear_session("session-1")

    with pytest.raises(UnknownNetworkContextError):
        registry.snapshot("session-1", session_one_context)


def test_context_snapshot_hides_auth_and_cookie_plaintext_from_repr() -> None:
    registry = NetworkContextRegistry()
    token_context = registry.create(
        "session-1",
        headers={"Authorization": "Bearer very-secret"},
        cookies={"session": "very-secret"},
        auth={"token": "very-secret"},
    )

    snapshot = registry.snapshot("session-1", token_context)

    assert "very-secret" not in repr(snapshot)


def test_context_registry_rejects_unknown_strategy() -> None:
    registry = NetworkContextRegistry()
    context = registry.create("session-1")

    with pytest.raises(ValueError, match="unsupported network context strategy"):
        registry.apply_strategy("session-1", context, strategy="invalid")


def test_context_registry_does_not_accept_missing_context_for_inherit() -> None:
    registry = NetworkContextRegistry()

    with pytest.raises(UnknownNetworkContextError):
        registry.apply_strategy("session-1", ExecutionTokenContext(), strategy="inherit")
