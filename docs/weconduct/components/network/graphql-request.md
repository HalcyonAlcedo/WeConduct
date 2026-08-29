---
product: weconduct
version: 0.9.1
doc_id: component:network.graphql_request
---

# 网络 GraphQL 请求

资源键：`network.graphql_request`　|　英文名：Network GraphQL Request
## 功能说明

通过网络运行时执行 GraphQL 查询或变更。

## 什么时候用

发送 GraphQL Query 或 Mutation，配置 endpoint、query、变量和扩展字段。

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
| `in:endpoint` | input | `data` | `in.endpoint` |
| `in:query` | input | `data` | `in.query` |
| `in:operation_name` | input | `data` | `in.operation_name` |
| `in:variables` | input | `data` | `in.variables` |
| `in:extensions` | input | `data` | `in.extensions` |
| `in:headers` | input | `data` | `in.headers` |
| `in:auth` | input | `data` | `in.auth` |
| `in:tls` | input | `data` | `in.tls` |
| `in:proxy` | input | `data` | `in.proxy` |
| `in:timeout` | input | `data` | `in.timeout` |
| `out:data` | output | `data` | `out.data` |
| `out:errors` | output | `data` | `out.errors` |
| `out:extensions` | output | `data` | `out.extensions` |
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
| `endpoint` | `string` | 是 | `""` | `default` |
| `query` | `string` | 是 | `""` | `default` |
| `operation_name` | `any` | 否 | `null` | `default` |
| `variables` | `object` | 否 | `{}` | `default` |
| `extensions` | `object` | 否 | `{}` | `default` |
| `headers` | `object` | 否 | `{}` | `default` |
| `timeout` | `integer` | 否 | `null` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:context_strategy`、`in:switch_context_id`、`in:endpoint`、`in:query`、`in:operation_name`、`in:variables`、`in:extensions`、`in:headers`、`in:auth`、`in:tls`、`in:proxy`、`in:timeout`。输出端口：`out`、`failed`、`out:data`、`out:errors`、`out:extensions`、`out:response`、`out:status_code`、`out:headers`、`out:body_ref`、`out:duration_ms`、`out:final_url`、`out:network_context_id`、`out:request_id`、`out:transport_error`。对外影响：访问 GraphQL 服务，并可能执行服务端 Mutation。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/network/network-graphql-request.json" title="网络 GraphQL 请求配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "context_strategy": "inherit",
  "endpoint": "https://example.com/graphql",
  "query": "example",
  "operation_name": null,
  "variables": {},
  "extensions": {},
  "headers": {},
  "timeout": null
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

返回 GraphQL data、errors、extensions 以及底层 HTTP 元数据。

## 常见问题

缺少必填参数：`endpoint`、`query`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；endpoint/query 无效、服务端返回 GraphQL errors、网络权限或认证配置错误。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

0.9.1 不支持 GraphQL Subscription；运行时会稳定拒绝该操作；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[网络自动化](index.md)聚合页查看更多同类节点。
- [网络 HTTP 请求](http-request.md) (`network.http_request`)。
- [网络上传](upload.md) (`network.upload`)。
- [网络下载](download.md) (`network.download`)。
- [网络响应断言](response-assert.md) (`network.response_assert`)。
- [网络 SSE 连接](sse-connect.md) (`network.sse_connect`)。
