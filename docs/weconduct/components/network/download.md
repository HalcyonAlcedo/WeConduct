---
product: weconduct
version: 0.9.0
doc_id: component:network.download
---

# 网络下载

资源键：`network.download`　|　英文名：Network Download
## 功能说明

将响应下载到会话级临时存储。

## 什么时候用

从 HTTP/HTTPS 目标下载响应内容，并把结果保存到网络运行时的会话临时资源。

## 需要什么权限

需要按目标地址开启本地或远程网络访问；需要开启浏览器下载和文件访问。

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
| `in:headers` | input | `data` | `in.headers` |
| `in:query` | input | `data` | `in.query` |
| `in:auth` | input | `data` | `in.auth` |
| `in:tls` | input | `data` | `in.tls` |
| `in:proxy` | input | `data` | `in.proxy` |
| `in:timeout` | input | `data` | `in.timeout` |
| `out:response` | output | `data` | `out.response` |
| `out:status_code` | output | `data` | `out.status_code` |
| `out:headers` | output | `data` | `out.headers` |
| `out:body_ref` | output | `data` | `out.body_ref` |
| `out:duration_ms` | output | `data` | `out.duration_ms` |
| `out:final_url` | output | `data` | `out.final_url` |
| `out:network_context_id` | output | `data` | `out.network_context_id` |
| `out:file_size` | output | `data` | `out.file_size` |
| `out:checksum_sha256` | output | `data` | `out.checksum_sha256` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `context_strategy` | `string` | 否 | `"inherit"` | `default` |
| `method` | `string` | 否 | `"GET"` | `default` |
| `url` | `string` | 是 | `""` | `default` |
| `headers` | `object` | 否 | `{}` | `default` |
| `query` | `object` | 否 | `{}` | `default` |
| `timeout` | `integer` | 否 | `null` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:context_strategy`、`in:switch_context_id`、`in:url`、`in:method`、`in:headers`、`in:query`、`in:auth`、`in:tls`、`in:proxy`、`in:timeout`。输出端口：`out`、`failed`、`out:response`、`out:status_code`、`out:headers`、`out:body_ref`、`out:duration_ms`、`out:final_url`、`out:network_context_id`、`out:file_size`、`out:checksum_sha256`。对外影响：访问网络目标并创建会话级临时下载资源。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/network/network-download.json" title="网络下载配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "context_strategy": "inherit",
  "method": "GET",
  "url": "https://example.com",
  "headers": {},
  "query": {},
  "timeout": null
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

下载完成后返回响应、文件大小、SHA-256 校验值和最终 URL。

## 常见问题

缺少必填参数：`url`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；目标不可访问、响应状态不符合预期、网络权限不足或临时资源写入失败。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

临时下载资源随执行会话清理；需要长期保存时显式使用文件节点持久化；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[网络自动化](index.md)聚合页查看更多同类节点。
- [网络 HTTP 请求](http-request.md) (`network.http_request`)。
- [网络上传](upload.md) (`network.upload`)。
- [网络响应断言](response-assert.md) (`network.response_assert`)。
- [网络 GraphQL 请求](graphql-request.md) (`network.graphql_request`)。
- [网络 SSE 连接](sse-connect.md) (`network.sse_connect`)。
