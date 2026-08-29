---
product: weconduct
version: 0.9.1
doc_id: component:network.http_request
---

# 网络 HTTP 请求

资源键：`network.http_request`　|　英文名：Network HTTP Request
## 功能说明

通过会话级网络运行时执行 HTTP 请求。

## 什么时候用

向 HTTP/HTTPS 目标发送 REST 请求；使用上下文策略继承认证、代理和会话状态，也可以通过数据端口覆盖本次请求。

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
| `in:url` | input | `data` | `in.url` |
| `in:method` | input | `data` | `in.method` |
| `in:body` | input | `data` | `in.body` |
| `in:headers` | input | `data` | `in.headers` |
| `in:query` | input | `data` | `in.query` |
| `in:auth` | input | `data` | `in.auth` |
| `in:tls` | input | `data` | `in.tls` |
| `in:proxy` | input | `data` | `in.proxy` |
| `in:timeout` | input | `data` | `in.timeout` |
| `in:retry_policy` | input | `data` | `in.retry_policy` |
| `out:response` | output | `data` | `out.response` |
| `out:status_code` | output | `data` | `out.status_code` |
| `out:headers` | output | `data` | `out.headers` |
| `out:body_ref` | output | `data` | `out.body_ref` |
| `out:duration_ms` | output | `data` | `out.duration_ms` |
| `out:final_url` | output | `data` | `out.final_url` |
| `out:network_context_id` | output | `data` | `out.network_context_id` |
| `out:request_id` | output | `data` | `out.request_id` |
| `out:transport_error` | output | `data` | `out.transport_error` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `context_strategy` | `string` | 否 | `"inherit"` | `default` |
| `switch_context_id` | `any` | 否 | `null` | `default` |
| `method` | `string` | 否 | `"GET"` | `default` |
| `url` | `string` | 是 | `""` | `default` |
| `headers` | `object` | 否 | `{}` | `default` |
| `query` | `object` | 否 | `{}` | `default` |
| `body` | `string` | 是 | `""` | `default` |
| `timeout` | `integer` | 否 | `null` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:context_strategy`、`in:switch_context_id`、`in:url`、`in:method`、`in:body`、`in:headers`、`in:query`、`in:auth`、`in:tls`、`in:proxy`、`in:timeout`、`in:retry_policy`。输出端口：`out`、`failed`、`out:response`、`out:status_code`、`out:headers`、`out:body_ref`、`out:duration_ms`、`out:final_url`、`out:network_context_id`、`out:request_id`、`out:transport_error`。对外影响：访问本地或远程网络目标，并可能对服务端产生写操作。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/network/network-http-request.json" title="网络 HTTP 请求配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "context_strategy": "inherit",
  "switch_context_id": null,
  "method": "GET",
  "url": "https://example.com",
  "headers": {},
  "query": {},
  "body": "example",
  "timeout": null
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

请求完成后返回响应摘要、状态码、响应头、响应体引用和请求元数据。

## 常见问题

缺少必填参数：`url`、`body`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；URL、方法或请求体无效，网络权限不足，认证/TLS/代理配置错误，连接超时或响应处理失败。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

敏感认证值在运行链路中可用，但日志、事件、历史和诊断只保留脱敏结果；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[网络自动化](index.md)聚合页查看更多同类节点。
- [网络上传](upload.md) (`network.upload`)。
- [网络下载](download.md) (`network.download`)。
- [网络响应断言](response-assert.md) (`network.response_assert`)。
- [网络 GraphQL 请求](graphql-request.md) (`network.graphql_request`)。
- [网络 SSE 连接](sse-connect.md) (`network.sse_connect`)。
