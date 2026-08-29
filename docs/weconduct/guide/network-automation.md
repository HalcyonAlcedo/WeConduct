---
product: weconduct
version: 0.9.1
doc_id: weconduct:guide:network-automation
---

# 网络自动化

0.9.1 将网络请求作为节点图中的标准执行能力。网络节点共享当前执行会话的网络上下文，能够复用基础地址、认证、代理、TLS、Cookie 和响应限制等运行配置，同时保留显式端口让节点覆盖本次执行参数。

## 执行上下文

网络上下文只属于当前运行会话，不会因为节点图保存而把临时认证状态写回项目文件。逻辑链上的后续网络节点可以继承前一个节点建立的上下文；需要隔离时，在节点配置中选择新的、匿名的或分支上下文。

常用策略如下：

| 策略 | 用途 |
|---|---|
| `inherit` | 继承当前逻辑链上的网络上下文，适合连续请求。 |
| `new` | 创建新的隔离上下文，不读取前一节点的会话状态。 |
| `anonymous` | 使用不带认证和会话材料的干净上下文。 |
| `fork` | 从当前上下文复制一份隔离分支，后续修改不回写父上下文。 |
| `switch` | 通过 `switch_context_id` 切换到已经存在的上下文。 |
| `reset` | 清理当前上下文的临时网络状态后继续执行。 |

配置优先级从高到低为：有效的输入端口、节点配置、网络上下文、程序级网络默认值。以 `network.http_request` 为例，`in:url`、`in:headers`、`in:auth`、`in:tls`、`in:proxy`、`in:timeout` 和 `in:retry_policy` 有有效数据时，会覆盖节点面板中的同名配置；没有输入时才使用节点配置和继承上下文。

会话结束、取消或失败收敛后，临时响应文件、连接句柄和上下文中的临时认证状态会清理。需要跨会话保存的数据，应通过文件节点或其他明确的持久化流程自行保存。

## 节点选择

- `network.http_request`：HTTP/1.1、HTTP/2、重定向、请求体和结构化响应。
- `network.graphql_request`：GraphQL Query 和 Mutation。
- `network.upload`、`network.download`：受控文件上传和会话级临时下载。
- `network.response_assert`：状态码、响应头、正文、JSONPath、Schema、耗时和大小断言。
- `network.batch_request`：按输入顺序输出结果，可通过 `max_concurrency=1` 强制串行。
- `network.sse_connect`：建立 SSE 连接后主动接收事件。
- `network.websocket_connect`：连接、发送、接收、ping 和关闭 WebSocket。

每个节点的完整端口和参数以[网络自动化节点参考](../components/network/index.md)为准。网络响应正文通过 `out:body_ref` 传递，后续节点应使用正文引用的读取能力，不要把大响应直接复制到多个节点配置中。

## 认证、TLS 与代理

网络节点支持静态 Basic/Bearer、OAuth Client Credentials 和 Refresh Token。认证、Cookie、客户端证书、私钥和自定义 CA 等敏感材料可以从输入端口或加密参数提供。日志、诊断、事件和运行历史只保留脱敏后的结构，不会显示敏感值。

TLS 配置支持系统 CA、自定义 CA、证书固定和 mTLS。代理可以使用直接连接、环境配置、手动 HTTP/SOCKS 配置以及 Windows/PAC 解析结果。程序和项目的网络访问权限仍然优先于节点配置；没有开启对应网络权限时，请求会在传输前被拒绝。

## 限制与协议边界

0.9.1 的 SSE 和 WebSocket 是主动拉取式节点：网络线程不会直接激活新的图分支，也不提供自动重连。`network.graphql_request` 只支持 Query/Mutation，GraphQL Subscription 会稳定返回“不支持”错误。

Cookie 在 0.9.1 只按名称和值在同一执行上下文中传递，不等同于浏览器级 Cookie Jar；domain、path、secure、SameSite 和同名不同作用域的完整规则属于后续版本。

统一长连接所有权、完整协议状态机、自动重连、统一连接 epoch 和推送式图激活属于方案 C，预计在 0.9.1 或 0.9.2 评估实施，不是当前版本能力。

## 常见问题

请求返回 4xx/5xx 时，先检查 `out:status_code`、`out:headers` 和 `out:body_ref`。这些是正常 HTTP 响应，不会自动变成节点失败；传输错误、策略拒绝、响应超限和超时才会进入失败路径。

如果后续节点没有继承认证或 Cookie，检查节点的 `context_strategy` 是否被设置为 `anonymous` 或 `new`，以及是否通过输入端口覆盖了上下文 ID。若需要多个互不影响的登录态，使用 `fork` 建立分支后再分别执行。
