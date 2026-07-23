from __future__ import annotations

import pytest

from weconduct.network_runtime.access_policy import NetworkAccessPolicy


def test_network_access_policy_blocks_loopback_by_default() -> None:
    policy = NetworkAccessPolicy()

    with pytest.raises(ValueError, match="network.access_denied"):
        policy.validate_url("http://127.0.0.1:8080/status")


def test_network_access_policy_allows_explicit_loopback_test_fixture() -> None:
    policy = NetworkAccessPolicy(allow_loopback=True)

    policy.validate_url("http://127.0.0.1:8080/status")


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest/meta-data", "http://10.0.0.1/"])
def test_network_access_policy_blocks_metadata_and_private_addresses(url: str) -> None:
    policy = NetworkAccessPolicy()

    with pytest.raises(ValueError, match="network.access_denied"):
        policy.validate_url(url)
