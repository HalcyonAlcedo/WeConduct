---
product: weconduct
version: 0.9.0
doc_id: component:network.response_assert
---

# 网络响应断言

资源键：`network.response_assert`　|　英文名：Network Response Assert
## 功能说明

使用结构化断言验证网络响应。

## 什么时候用

对前一个网络节点的响应执行状态码、响应头、正文、JSON、Schema、URL 或耗时断言。

## 需要什么权限

需要按目标地址开启本地或远程网络访问。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `passed` | output | `control` | `out.passed` |
| `failed` | output | `control` | `out.failed` |
| `in:response` | input | `data` | `in.response` |
| `out:response` | output | `data` | `out.response` |
| `out:assertion_report` | output | `data` | `out.assertion_report` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `expected_status_codes` | `any` | 否 | `null` | `default` |
| `required_headers` | `object` | 否 | `{}` | `default` |
| `body_contains` | `any` | 否 | `null` | `default` |
| `json_path_equals` | `object` | 否 | `{}` | `default` |
| `json_schema` | `any` | 否 | `null` | `default` |
| `expected_final_url` | `any` | 否 | `null` | `default` |
| `require_no_graphql_errors` | `boolean` | 否 | `false` | `default` |
| `max_duration_ms` | `integer` | 否 | `null` | `default` |
| `max_size_bytes` | `any` | 否 | `null` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:response`。输出端口：`passed`、`failed`、`out:response`、`out:assertion_report`。对外影响：读取响应并选择通过或失败控制分支。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/network/network-response-assert.json" title="网络响应断言配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "expected_status_codes": null,
  "required_headers": {},
  "body_contains": null,
  "json_path_equals": "output/example.txt",
  "json_schema": null,
  "expected_final_url": null,
  "require_no_graphql_errors": false,
  "max_duration_ms": null,
  "max_size_bytes": null
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

断言通过时从 `passed` 继续，失败时从 `failed` 继续，并输出断言报告。

## 常见问题

端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；输入不是响应对象、断言规则格式错误或响应不满足条件。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

该节点不重新发送请求；必须连接已有网络响应；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[网络自动化](index.md)聚合页查看更多同类节点。
- [网络 HTTP 请求](http-request.md) (`network.http_request`)。
- [网络上传](upload.md) (`network.upload`)。
- [网络下载](download.md) (`network.download`)。
- [网络 GraphQL 请求](graphql-request.md) (`network.graphql_request`)。
- [网络 SSE 连接](sse-connect.md) (`network.sse_connect`)。
