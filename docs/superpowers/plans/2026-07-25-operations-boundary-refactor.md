# Operations Boundary Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 使 0.9.0 的操作契约和外部 API 实现落到正式设计指定的独立物理边界，同时保持所有公开 API/CLI 行为不变。

**Architecture:** `weconduct.application.operations` 保存 descriptor、只读 registry 与执行委托服务；`weconduct.api.external_v1` 保存 bearer 鉴权与 HTTP/SSE operation adapter。`api/server.py` 继续拥有 HTTP 基础设施和内部 UI API，但外部 v1 入口只创建 router 并委托它处理请求。

**Tech Stack:** Python 3.13、标准库 `http.server`、pytest。

---

### Task 1: 锁定正式物理边界

**Files:**

- Create: `tests/architecture/test_090_operations_boundaries.py`
- Create: `src/weconduct/application/operations/__init__.py`
- Create: `src/weconduct/api/external_v1/__init__.py`
- Modify: `src/weconduct/api/server.py`

- [x] **Step 1: Write the failing test**

```python
import inspect

from weconduct.api.server import WeConductApiHandler


def test_090_operations_and_external_v1_are_explicit_packages() -> None:
    from weconduct.application.operations import HostOperationService, OperationRegistry
    from weconduct.api.external_v1.router import ExternalV1Router

    assert HostOperationService.__module__.startswith("weconduct.application.operations")
    assert OperationRegistry.__module__.startswith("weconduct.application.operations")
    assert ExternalV1Router.__module__ == "weconduct.api.external_v1.router"


def test_090_external_v1_handler_entry_is_thin_router_delegation() -> None:
    source = inspect.getsource(WeConductApiHandler._handle_external_api)
    assert "ExternalV1Router" in source
    assert "_resolve_external_operation" not in source
```

- [x] **Step 2: Run the RED test**

```powershell
python -m pytest tests/architecture/test_090_operations_boundaries.py -q
```

预期：因 `weconduct.application.operations` 和 `weconduct.api.external_v1` 不存在而失败。

- [x] **Step 3: Create package roots and reduce the handler entry to a router delegation**

```python
def _handle_external_api(self, *, method: str) -> bool:
    return ExternalV1Router(self).handle(method=method)
```

不得把认证、路由映射、幂等、错误状态或 SSE 循环留在该方法内。

- [x] **Step 4: Run the boundary test after the package roots exist**

```powershell
python -m pytest tests/architecture/test_090_operations_boundaries.py -q
```

预期：第一个断言在 `HostOperationService` 尚未迁移时失败；入口委托断言可通过。

### Task 2: Split descriptor, registry and execution service

**Files:**

- Create: `src/weconduct/application/operations/models.py`
- Create: `src/weconduct/application/operations/registry.py`
- Create: `src/weconduct/application/operations/service.py`
- Modify: `src/weconduct/application/operations/__init__.py`
- Modify: `src/weconduct/application/operation_registry.py`
- Modify: `src/weconduct/application/__init__.py`
- Modify: `src/weconduct/cli/main.py`
- Modify: `tests/application/test_operation_registry.py`

- [x] **Step 1: Write the failing test**

```python
from weconduct.application.operations import HostOperationService, OperationRegistry


def test_operation_service_executes_through_explicit_registry() -> None:
    registry = OperationRegistry.build_stable_public()
    service = HostOperationService(service=_FakeService(), registry=registry)

    assert service.execute("graph.replace", {"graph_document": {}, "expected_revision": 4})["status"] == "saved"
```

- [x] **Step 2: Run the RED test**

```powershell
python -m pytest tests/application/test_operation_registry.py::test_operation_service_executes_through_explicit_registry -q
```

预期：`OperationRegistry.build_stable_public` 或 `HostOperationService` 缺失。

- [x] **Step 3: Move implementation by responsibility**

`models.py` 仅定义 `OperationDescriptor` 和 `OperationRegistryError`；`registry.py` 仅保存显式 `stable_public` descriptor 与输入校验；`service.py` 保存 `HostOperationService.execute()`、具体业务委托、输出筛选、敏感遮罩和 ValueError 归一化。旧 `application/operation_registry.py` 只能 re-export 新包类型，不能保留实现。

- [x] **Step 4: Migrate internal call sites and run GREEN tests**

```powershell
python -m pytest tests/application/test_operation_registry.py tests/cli/test_operation_adapter.py -q
```

预期：全部通过；CLI 直接使用 `HostOperationService`，不通过 Python 方法名反射调用服务。

### Task 3: Split External API authentication and operation adapter

**Files:**

- Create: `src/weconduct/api/external_v1/auth.py`
- Create: `src/weconduct/api/external_v1/router.py`
- Modify: `src/weconduct/api/external_v1/__init__.py`
- Modify: `src/weconduct/api/server.py`
- Modify: `tests/api/test_external_api.py`
- Modify: `tests/architecture/test_090_operations_boundaries.py`

- [x] **Step 1: Write the failing test**

```python
def test_external_router_keeps_bearer_semantics_and_maps_the_fixed_host_route() -> None:
    from weconduct.api.external_v1.auth import ExternalApiAuthenticator
    from weconduct.api.external_v1.router import resolve_external_operation

    assert ExternalApiAuthenticator(expected_token="token").accepts("Bearer token")
    assert resolve_external_operation(method="GET", request_path="/api/ext/v1/host") == ("host.describe", {})
```

- [x] **Step 2: Run the RED test**

```powershell
python -m pytest tests/api/test_external_api.py::test_external_router_keeps_bearer_semantics_and_maps_the_fixed_host_route -q
```

预期：`ExternalApiAuthenticator` 与 `resolve_external_operation` 未定义。

- [x] **Step 3: Move protocol implementation**

`auth.py` 只实现显式 bearer token 检查；`router.py` 实现固定路由映射、registry/service 调用、幂等、错误 HTTP 映射及 SSE 写入。Router 通过窄 handler protocol 使用 `_get_service()`、`_write_json()`、`_read_optional_json_request_body()` 和 HTTP writer；不复制内部 UI API 路由。

- [x] **Step 4: Run external API GREEN and adjacent regression tests**

```powershell
python -m pytest tests/architecture/test_090_operations_boundaries.py tests/api/test_external_api.py tests/cli/test_operation_adapter.py -q
```

预期：全部通过；缺失/错误 bearer token、SSE 游标、待输入 202/409/410、幂等与内部 UI API 均保持原契约。

### Task 4: Close verification and records

**Files:**

- Modify: `../docs/dev/version-0.9/2026-07-23-version-0.9.0-progress-tracker.md`
- Modify: `../docs/dev/version-0.9/2026-07-23-version-0.9.0-issue-feedback.md`

- [x] **Step 1: Run layered regression**

```powershell
python -m pytest tests/application/test_operation_registry.py tests/api/test_external_api.py tests/cli/test_operation_adapter.py tests/integration/test_090_external_api_workflow.py -q
python -m pytest tests/architecture/test_090_operations_boundaries.py -q
```

- [x] **Step 2: Record the design-conformance repair**

进度记录必须写入新包路径、测试命令、退出码和日期；问题记录新增设计一致性问题并在验证后关闭。

- [x] **Step 3: Commit**

```powershell
git add src/weconduct/application/operations src/weconduct/api/external_v1 src/weconduct/application/operation_registry.py src/weconduct/application/__init__.py src/weconduct/api/server.py src/weconduct/cli/main.py tests/architecture tests/application/test_operation_registry.py tests/api/test_external_api.py tests/cli/test_operation_adapter.py
git commit -m 'refactor: isolate operation and external API boundaries'
```
