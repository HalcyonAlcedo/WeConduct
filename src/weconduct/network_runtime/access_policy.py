from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlsplit


_METADATA_ADDRESSES = frozenset({"169.254.169.254", "fd00:ec2::254"})


@dataclass(frozen=True)
class ResolvedNetworkTarget:
    hostname: str
    port: int
    addresses: tuple[str, ...]


@dataclass(frozen=True)
class NetworkAccessPolicy:
    """Validates destination addresses before a network connection is opened."""

    allow_loopback: bool = False
    allowed_hostnames: frozenset[str] = field(default_factory=frozenset)

    def validate_url(
        self,
        url: str,
        *,
        allowed_schemes: frozenset[str] = frozenset({"http", "https"}),
    ) -> ResolvedNetworkTarget | None:
        parsed = urlsplit(url)
        if parsed.scheme not in allowed_schemes or not parsed.hostname:
            allowed = ", ".join(sorted(allowed_schemes))
            raise ValueError(f"network.access_denied: only absolute {allowed} URLs are allowed")
        hostname = parsed.hostname.lower()
        if hostname in {item.lower() for item in self.allowed_hostnames}:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return ResolvedNetworkTarget(
            hostname=hostname,
            port=port,
            addresses=self.resolve_connect_addresses(hostname, port),
        )

    def resolve_connect_addresses(self, hostname: str, port: int | None) -> tuple[str, ...]:
        """Resolve a connection target once and reject disallowed addresses.

        The returned addresses are intended for the socket layer. Callers must
        connect to one of them instead of resolving ``hostname`` again.
        """
        normalized_hostname = hostname.strip().lower()
        if not normalized_hostname:
            raise ValueError("network.access_denied: hostname is required")
        is_explicitly_allowed = normalized_hostname in {
            item.lower() for item in self.allowed_hostnames
        }
        try:
            addresses = tuple(
                record[4][0]
                for record in socket.getaddrinfo(
                    normalized_hostname,
                    port,
                    type=socket.SOCK_STREAM,
                )
            )
        except OSError as exc:
            raise ValueError("network.access_denied: hostname resolution failed") from exc
        if not addresses:
            raise ValueError("network.access_denied: hostname resolved to no addresses")
        if not is_explicitly_allowed:
            for address in addresses:
                self._validate_address(address)
        return tuple(dict.fromkeys(addresses))

    def _validate_address(self, address: str) -> None:
        try:
            parsed_address = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError("network.access_denied: invalid resolved address") from exc
        if str(parsed_address) in _METADATA_ADDRESSES:
            raise ValueError("network.access_denied: metadata addresses are blocked")
        if parsed_address.is_loopback and self.allow_loopback:
            return
        if (
            parsed_address.is_loopback
            or parsed_address.is_private
            or parsed_address.is_link_local
            or parsed_address.is_multicast
            or parsed_address.is_unspecified
        ):
            raise ValueError("network.access_denied: non-public addresses are blocked")
