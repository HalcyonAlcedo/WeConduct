---
product: weconduct
version: 0.9.1
doc_id: weconduct:guide:external-api
---

# 外部 API

0.9.1 提供本机外部操作接口，基地址为 `/api/ext/v1`。它适合脚本、CLI 适配器和本地工具管理项目、图、运行会话和 Debug 会话。本页描述当前版本的受控操作边界，不代表跨机器、长期压力或公网部署保证。

## 启用与鉴权

在 **文件 → 首选项 → 安全** 中启用外部 API，设置独立 Bearer Token、端口和允许的项目根目录。`external_api_port = 0` 表示每次启动使用动态端口；固定端口修改后需要重启程序。外部 Token 属于软件首选项，不属于项目加密参数，允许在首选项中直接查看、修改和清除。

每次请求都使用：

```http
Authorization: Bearer <external-api-token>
```

缺失或错误 Token 返回 `401`；外部 API 被禁用时返回 `404 external_api.disabled`。外部 Bearer Token 与桌面 UI 使用的进程内 `X-WeConduct-Token` 完全分离，不能互相替代。程序默认只绑定 loopback；CLI 只有在明确使用 `--allow-non-loopback` 后才允许非 loopback 监听，这属于高风险部署方式。不要把端口、CORS 或 Origin 检查当作身份认证替代品。

## 当前支持的基础操作

当前支持的操作按资源类型分组如下。完整的稳定公开操作清单可通过
`GET /api/ext/v1/operations` 获取，单项详情可通过
`GET /api/ext/v1/operations/{operation_id}` 查询。

`.wcsubgraph` 文件的选择、导出和导入提交属于桌面资源管理操作；它们使用工作台接口，不在 `/api/ext/v1` 的稳定公开操作清单中。

- `GET /api/ext/v1/host`、`GET /api/ext/v1/host/capabilities`：查询实例、版本和能力声明；
- `POST /api/ext/v1/projects`、`POST /api/ext/v1/project/open`、`GET /api/ext/v1/project/current`、`GET /api/ext/v1/project/resource-audit`、`POST /api/ext/v1/project/save`、`POST /api/ext/v1/project/close`：管理项目并检查项目资源；
- `GET /api/ext/v1/graph`、`PUT /api/ext/v1/graph`、`POST /api/ext/v1/graph/validate`、`POST /api/ext/v1/graph/compile`、`POST /api/ext/v1/graph/node-drafts`：读取、替换、校验、编译和创建节点草稿；
- `POST /api/ext/v1/graph/normalize`、`POST /api/ext/v1/graph/context`、`POST /api/ext/v1/graph/patch/preview`、`POST /api/ext/v1/graph/patch`：规范化、读取图上下文以及预览/应用图补丁；
- `GET /api/ext/v1/graph/documents`、`GET /api/ext/v1/graph/documents/{document_id}`、`PUT /api/ext/v1/graph/documents/{document_id}`、`GET /api/ext/v1/graph/source-projection`：读取和替换图文档、查询源投影；
- `POST /api/ext/v1/executions`、`GET /api/ext/v1/executions/{execution_id}`、`POST /api/ext/v1/executions/{execution_id}/cancel`：启动、查询和取消执行；
- `POST /api/ext/v1/executions/prepare`、`GET /api/ext/v1/runtimes`、`GET /api/ext/v1/execution-history`：执行预检、运行时目录和执行历史；
- `POST /api/ext/v1/executions/{execution_id}/unlock`：提交加密参数解锁密码；
- `GET /api/ext/v1/executions/{execution_id}/events`：订阅执行事件；
- `GET /api/ext/v1/executions/{execution_id}/pending-input`、`POST /api/ext/v1/executions/{execution_id}/pending-input/{request_id}/submit`：查询和提交待输入表单。
- `GET /api/ext/v1/resources`、`GET /api/ext/v1/components`、`POST /api/ext/v1/resources/user-components`、`POST /api/ext/v1/resources/subgraphs`、`POST /api/ext/v1/resources/custom-node-graphs`、`POST /api/ext/v1/resources/custom-node-graphs/empty`：查询组件/资源目录、保存或创建用户组件；
- `POST /api/ext/v1/resources/{resource_id}/enabled`、`POST /api/ext/v1/resources/{resource_id}/tags`、`POST /api/ext/v1/resources/metadata`、`POST /api/ext/v1/resources/rename`、`POST /api/ext/v1/resources/delete`：修改资源启用状态、标签、元数据、名称和删除资源；
- `GET /api/ext/v1/configuration/{scope}/schema`、`GET /api/ext/v1/configuration/{scope}/values`、`POST /api/ext/v1/configuration/{scope}/preview`、`POST /api/ext/v1/configuration/{scope}/apply`、`POST /api/ext/v1/configuration/{scope}/reset`：查询、预览和应用程序/项目/图配置。
- `POST /api/ext/v1/debug/prepare`、`POST /api/ext/v1/debug`、`GET /api/ext/v1/debug`：准备、启动和列出 Debug 会话；
- `GET /api/ext/v1/debug/{session_id}`、`POST /api/ext/v1/debug/{session_id}/continue`、`POST /api/ext/v1/debug/{session_id}/pause`：查询、继续和暂停 Debug；
- `POST /api/ext/v1/debug/{session_id}/step-over`、`POST /api/ext/v1/debug/{session_id}/step-into`、`POST /api/ext/v1/debug/{session_id}/step-out`、`POST /api/ext/v1/debug/{session_id}/abort`：单步和终止 Debug；
- `GET /api/ext/v1/debug/history`、`GET /api/ext/v1/debug/history/{session_id}`、`GET /api/ext/v1/debug/history/{session_id}/events`、`GET /api/ext/v1/debug/history/{session_id}/projection`：读取 Debug 历史、事件和投影；
- `GET /api/ext/v1/debug/{session_id}/projection`、`POST /api/ext/v1/debug/{session_id}/variables`、`POST /api/ext/v1/debug/{session_id}/node-debugger`、`POST /api/ext/v1/debug/{session_id}/unlock`：读取实时投影、应用变量/节点调试修改和解锁 Debug 参数。

修改项目或图时使用 `Idempotency-Key`，并带上服务端返回的 `revision`。revision 不匹配会返回冲突，客户端应重新读取后再决定是否覆盖；不要把冲突自动静默重试为覆盖操作。

## 执行与事件

Debug 会话的状态机与桌面 Debug 面板一致：先 `debug.prepare`，再 `debug.start`，随后使用
`debug.get`、继续/暂停/单步或 `debug.abort` 控制。历史接口返回只读事件和投影；变量和节点调试
修改只提交到当前会话，不会写回项目图。

执行启动可能返回 `running`、`waiting` 或 `unlock_required`。收到 `waiting` 时先查询 pending-input；收到 `unlock_required` 时调用 unlock 操作。解锁成功后只返回参数 ID 和状态，不返回明文参数。

执行事件使用 `text/event-stream`，支持 `Last-Event-ID` 续读、终态事件和服务端 heartbeat。游标过期时会返回可用于重新读取的事件边界；客户端应重新获取执行快照，再从新的游标继续订阅。断开 SSE 不会自动取消执行，取消必须调用 cancel 操作。

外部 API 成功修改项目、图或执行状态后，已打开的桌面 UI 会通过工作台事件流同步项目、revision、Runtime 面板和节点状态。本地 UI 存在未保存图修改时，会显示 revision 冲突，不会静默覆盖本地草稿。

## 敏感数据边界

响应、错误、事件、运行历史和诊断不会包含加密参数、待输入敏感值或外部 Token 明文。Debug 变量读取和修改只作用于已授权的 Debug 会话，不能绕过项目解锁策略。测试脚本应使用独立 Token 和测试项目，并避免把 Authorization header、密码或敏感字段写入日志。

## 当前限制

0.9.1 外部 API 覆盖项目、图、资源、配置、运行、待输入和 Debug 操作；不提供插件管理、任意本机文件路径、非 loopback 公网服务、跨机器兼容性认证或长期压力保证。GraphQL Subscription、插件系统、方案 C 的统一长连接内核和推送式图激活也不属于当前版本。
