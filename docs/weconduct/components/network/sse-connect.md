---
product: weconduct
version: 0.9.1
doc_id: component:network.sse_connect
---

# 网络 SSE 连接

资源键：`network.sse_connect`　|　英文名：Network SSE Connection
## 功能说明

连接会话级 SSE 流并拉取事件。

## 什么时候用

以拉取式操作连接 SSE 端点，使用 `action` 选择 connect、receive 或 close。

## 需要什么权限

需要按目标地址开启本地或远程网络访问。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |
| `failed` | output | `control` | `out.failed` |
| `in:context_strategy` | input | `data` | `in.context_strategy` |
| `in:switch_context_id` | input | `data` | `in.switch_context_id` |
| `in:action` | input | `data` | `in.action` |
| `in:connection_id` | input | `data` | `in.connection_id` |
| `in:url` | input | `data` | `in.url` |
| `in:headers` | input | `data` | `in.headers` |
| `in:query` | input | `data` | `in.query` |
| `in:auth` | input | `data` | `in.auth` |
| `in:tls` | input | `data` | `in.tls` |
| `in:proxy` | input | `data` | `in.proxy` |
| `in:timeout` | input | `data` | `in.timeout` |
| `out:connection_id` | output | `data` | `out.connection_id` |
| `out:event` | output | `data` | `out.event` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `context_strategy` | `string` | 否 | `"inherit"` | `default` |
| `action` | `string` | 否 | `"connect"` | `default` |
| `connection_id` | `string` | 是 | `""` | `default` |
| `url` | `string` | 是 | `""` | `default` |
| `headers` | `object` | 否 | `{}` | `default` |
| `timeout_seconds` | `any` | 否 | `null` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:context_strategy`、`in:switch_context_id`、`in:action`、`in:connection_id`、`in:url`、`in:headers`、`in:query`、`in:auth`、`in:tls`、`in:proxy`、`in:timeout`。输出端口：`out`、`failed`、`out:connection_id`、`out:event`。对外影响：创建或消费会话级 SSE 连接。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/network/network-sse-connect.json" title="网络 SSE 连接配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "context_strategy": "inherit",
  "action": "connect",
  "connection_id": "example",
  "url": "https://example.com/events",
  "headers": {},
  "timeout_seconds": null
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

connect 返回连接 ID，receive 返回事件，close 释放连接登记

## 常见问题

缺少必填参数：`connection_id`、`url`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；端点不可访问、连接 ID 不存在、认证/TLS/代理失败或读取超时。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

0.9.1 是主动拉取式基础操作，不是推送事件源，也不提供方案 C 的自动重连；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[网络自动化](index.md)聚合页查看更多同类节点。
- [网络 HTTP 请求](http-request.md) (`network.http_request`)。
- [网络上传](upload.md) (`network.upload`)。
- [网络下载](download.md) (`network.download`)。
- [网络响应断言](response-assert.md) (`network.response_assert`)。
- [网络 GraphQL 请求](graphql-request.md) (`network.graphql_request`)。
