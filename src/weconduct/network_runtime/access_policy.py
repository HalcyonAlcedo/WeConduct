from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlsplit


_METADATA_ADDRESSES = frozenset({"169.254.169.254", "fd00:ec2::254"})


@dataclass(frozen=True)
class NetworkAccessPolicy:
    """Validates destination addresses before a network connection is opened."""

    allow_loopback: bool = False
    allowed_hostnames: frozenset[str] = field(default_factory=frozenset)

    def validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("network.access_denied: only absolute http(s) URLs are allowed")
        hostname = parsed.hostname.lower()
        if hostname in {item.lower() for item in self.allowed_hostnames}:
            return
        try:
            addresses = {
                record[4][0]
                for record in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
            }
        except OSError as exc:
            raise ValueError("network.access_denied: hostname resolution failed") from exc
        if not addresses:
            raise ValueError("network.access_denied: hostname resolved to no addresses")
        for address in addresses:
            self._validate_address(address)

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
