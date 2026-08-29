---
product: weconduct
version: 0.9.1
doc_id: component:network.upload
---

# 网络上传

资源键：`network.upload`　|　英文名：Network Upload
## 功能说明

通过会话级网络运行时流式上传受控本地文件。

## 什么时候用

把允许目录中的文件或运行时数据上传到 HTTP/HTTPS 目标，支持 multipart 字段和校验值。

## 需要什么权限

需要按目标地址开启本地或远程网络访问；需要开启文件访问，并确保上传文件位于允许的目录范围内；需要开启浏览器上传和文件访问。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |
| `failed` | output | `control` | `out.failed` |
| `in:context_strategy` | input | `data` | `in.context_strategy` |
| `in:switch_context_id` | input | `data` | `in.switch_context_id` |
| `in:url` | input | `data` | `in.url` |
| `in:source` | input | `data` | `in.source` |
| `in:file_path` | input | `data` | `in.file_path` |
| `in:field_name` | input | `data` | `in.field_name` |
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
| `out:uploaded_size` | output | `data` | `out.uploaded_size` |
| `out:source_checksum_sha256` | output | `data` | `out.source_checksum_sha256` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `context_strategy` | `string` | 否 | `"inherit"` | `default` |
| `url` | `string` | 是 | `""` | `default` |
| `file_path` | `string` | 是 | `""` | `default` |
| `source` | `any` | 否 | `null` | `default` |
| `field_name` | `string` | 否 | `"file"` | `default` |
| `file_name` | `any` | 否 | `null` | `default` |
| `multipart` | `boolean` | 否 | `false` | `default` |
| `multipart_fields` | `object` | 否 | `{}` | `default` |
| `media_type` | `string` | 否 | `"application/octet-stream"` | `default` |
| `checksum_sha256` | `any` | 否 | `null` | `default` |
| `max_upload_bytes` | `any` | 否 | `null` | `default` |
| `headers` | `object` | 否 | `{}` | `default` |
| `query` | `object` | 否 | `{}` | `default` |
| `timeout` | `integer` | 否 | `null` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:context_strategy`、`in:switch_context_id`、`in:url`、`in:source`、`in:file_path`、`in:field_name`、`in:headers`、`in:query`、`in:auth`、`in:tls`、`in:proxy`、`in:timeout`。输出端口：`out`、`failed`、`out:response`、`out:status_code`、`out:headers`、`out:body_ref`、`out:duration_ms`、`out:final_url`、`out:network_context_id`、`out:uploaded_size`、`out:source_checksum_sha256`。对外影响：读取本地文件并向网络目标上传数据。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/network/network-upload.json" title="网络上传配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "context_strategy": "inherit",
  "url": "https://example.com",
  "file_path": "output/example.txt",
  "source": null,
  "field_name": "file",
  "file_name": null,
  "multipart": false,
  "multipart_fields": {},
  "media_type": "application/octet-stream",
  "checksum_sha256": null,
  "max_upload_bytes": null,
  "headers": {},
  "query": {},
  "timeout": null
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

上传完成后返回响应、上传字节数、源校验值和请求元数据。

## 常见问题

缺少必填参数：`url`、`file_path`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；文件路径越界、文件不可读、目标拒绝上传、网络权限或认证配置错误。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

上传文件受文件访问允许根和大小限制约束；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[网络自动化](index.md)聚合页查看更多同类节点。
- [网络 HTTP 请求](http-request.md) (`network.http_request`)。
- [网络下载](download.md) (`network.download`)。
- [网络响应断言](response-assert.md) (`network.response_assert`)。
- [网络 GraphQL 请求](graphql-request.md) (`network.graphql_request`)。
- [网络 SSE 连接](sse-connect.md) (`network.sse_connect`)。
