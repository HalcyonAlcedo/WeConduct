from __future__ import annotations

import base64
from typing import Mapping


def apply_static_auth(headers: Mapping[str, str], auth: object) -> dict[str, str]:
    """Apply the supported static snapshot credentials unless a node overrides them."""
    effective = {str(name): str(value) for name, value in headers.items()}
    if any(name.lower() == "authorization" for name in effective):
        return effective
    if not isinstance(auth, Mapping):
        return effective
    auth_type = auth.get("type")
    if not isinstance(auth_type, str):
        return effective
    normalized_type = auth_type.strip().lower()
    if normalized_type == "bearer":
        token = auth.get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("network.auth_invalid")
        effective["Authorization"] = f"Bearer {token}"
    elif normalized_type == "basic":
        username = auth.get("username")
        password = auth.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError("network.auth_invalid")
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        effective["Authorization"] = f"Basic {encoded}"
    return effective
