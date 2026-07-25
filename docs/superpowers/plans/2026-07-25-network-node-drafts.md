# Network Node Drafts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 让 0.9.0 已注册的网络能力创建为具备控制、配置输入与结构化输出端口的可编译图节点。

**Architecture:** 将每类网络节点的稳定端口和初始配置放入 `builtin_components/node_drafts.py`，继续复用通用 `build_graph_node_draft()` 与 Vue Flow 的端口渲染。草稿只提供默认值和 schema，不在 UI 层复制网络运行时逻辑。

**Tech Stack:** Python、Pydantic 图模型、pytest。

---

### Task 1: 写入基础网络节点草稿

**Files:**

- Create: `tests/application/test_network_node_drafts_090.py`
- Modify: `src/weconduct/builtin_components/node_drafts.py`

- [x] **Step 1: Write the failing test**

```python
def test_network_http_request_draft_has_context_overrides_and_response_outputs() -> None:
    draft = CompilationWorkbenchService().build_graph_node_draft(resource_key="network.http_request")
    ports = {item["port_id"] for item in draft["node"]["ports"]}

    assert {"in", "in:url", "in:headers", "in:auth", "in:tls", "in:proxy", "in:timeout", "out:response", "out:status_code", "out:body_ref"} <= ports
    assert draft["node"]["node_config"]["context_strategy"] == "inherit"
```

- [x] **Step 2: Run the RED test**

```powershell
python -m pytest tests/application/test_network_node_drafts_090.py -q
```

预期：当前 draft 的 `ports == []`，断言失败。

- [x] **Step 3: Add HTTP, upload, download and response assertion definitions**

HTTP 草稿固定提供控制 `in/out/failed`，数据输入 `url/method/headers/query/body/auth/tls/proxy/timeout/retry`，及 `response/status_code/headers/body_ref/duration_ms/final_url/request_id/transport_error` 输出。上传和下载复用请求覆盖输入，响应断言提供 `response` 输入与 `passed/failed/response/assertion_report` 输出。

- [x] **Step 4: Run GREEN tests**

```powershell
python -m pytest tests/application/test_network_node_drafts_090.py -q
```

### Task 2: 完成 GraphQL、长连接与批量草稿

**Files:**

- Modify: `tests/application/test_network_node_drafts_090.py`
- Modify: `src/weconduct/builtin_components/node_drafts.py`

- [x] **Step 1: Write the failing test**

```python
def test_network_long_connection_and_batch_drafts_have_pull_actions_and_ordered_results() -> None:
    service = CompilationWorkbenchService()
    sse = service.build_graph_node_draft(resource_key="network.sse_connect")["node"]
    batch = service.build_graph_node_draft(resource_key="network.batch_request")["node"]

    assert {"in:connection_id", "out:event", "out:connection_id"} <= _port_ids(sse)
    assert {"in:requests", "out:results"} <= _port_ids(batch)
    assert batch["node_config"]["max_concurrency"] == 1
```

- [x] **Step 2: Run the RED test**

```powershell
python -m pytest tests/application/test_network_node_drafts_090.py -q
```

预期：GraphQL、SSE、WebSocket 和 batch 当前没有端口，断言失败。

- [x] **Step 3: Add GraphQL, SSE, WebSocket and batch definitions**

GraphQL 提供 endpoint/query/operation_name/variables/extensions 与安全覆盖输入；SSE/WS 提供明确 `action`、`connection_id`、消息或 ping 输入及拉取式事件输出；batch 默认 `max_concurrency=1` 并输出保持输入顺序的 `results`。所有节点拥有当前会话内 `context_strategy` 控制项。

- [x] **Step 4: Run GREEN and graph-model tests**

```powershell
python -m pytest tests/application/test_network_node_drafts_090.py tests/application/test_compilation_workbench_service.py -q
```

### Task 3: 收口

**Files:**

- Modify: `../docs/dev/version-0.9/2026-07-23-version-0.9.0-progress-tracker.md`
- Modify: `../docs/dev/version-0.9/2026-07-23-version-0.9.0-issue-feedback.md`

- [x] **Step 1: Run focused runtime and draft regression**

```powershell
python -m pytest tests/application/test_network_node_drafts_090.py tests/application/test_graph_upgrades_090.py tests/runtime/test_network_long_connection_nodes.py tests/runtime/test_network_graphql_request.py tests/runtime/test_network_response_assert.py -q
```

- [x] **Step 2: Record the repaired design gap**

记录旧行为“注册但只能创建空节点”、新端口契约、命令、退出码与日期。

- [x] **Step 3: Commit**

```powershell
git add src/weconduct/builtin_components/node_drafts.py tests/application/test_network_node_drafts_090.py
git commit -m 'feat: add network node graph drafts'
```
