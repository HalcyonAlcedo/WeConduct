from __future__ import annotations

from dataclasses import dataclass
import secrets


@dataclass(frozen=True)
class ExternalApiAuthenticator:
    """独立于内部 UI token 的 v1 Bearer 鉴权器。"""

    expected_token: str | None

    def accepts(self, authorization: str) -> bool:
        scheme, _, provided_token = authorization.partition(" ")
        return (
            isinstance(self.expected_token, str)
            and bool(self.expected_token)
            and scheme.lower() == "bearer"
            and bool(provided_token)
            and secrets.compare_digest(provided_token, self.expected_token)
        )
