"""0.9.0 前的导入位置；实现已迁移到 ``application.operations``。"""

from __future__ import annotations

from typing import Mapping

from .operations import HostOperationService, OperationDescriptor, OperationRegistryError


class OperationRegistry(HostOperationService):
    """兼容旧构造签名的薄壳；所有实现位于 ``application.operations``。"""

    def __init__(self, *, service: object, host_metadata: Mapping[str, object] | None = None) -> None:
        super().__init__(service=service, host_metadata=host_metadata)
