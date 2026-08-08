---
product: weconduct
version: 0.9.0
doc_id: component:network.batch_request
---

# 网络批量请求

资源键：`network.batch_request`　|　英文名：Network Batch Request
## 功能说明

以有界并发执行并按输入顺序返回网络请求。

## 什么时候用

在一个网络节点中按输入请求列表执行有界并发批量请求。

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
| `in:requests` | input | `data` | `in.requests` |
| `in:max_concurrency` | input | `data` | `in.max_concurrency` |
| `out:results` | output | `data` | `out.results` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `context_strategy` | `string` | 否 | `"inherit"` | `default` |
| `requests` | `array` | 否 | `[]` | `default` |
| `max_concurrency` | `integer` | 否 | `1` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:context_strategy`、`in:switch_context_id`、`in:requests`、`in:max_concurrency`。输出端口：`out`、`failed`、`out:results`。对外影响：向多个网络目标发起请求并消耗网络运行时资源。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/network/network-batch-request.json" title="网络批量请求配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "context_strategy": "inherit",
  "requests": [],
  "max_concurrency": 1
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

返回与请求顺序对应的结果列表；并发度受 `max_concurrency` 限制

## 常见问题

端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；请求列表结构错误、并发度无效、单项请求失败或网络策略拒绝目标。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

节点内支持有界并发；图级调度仍保持逻辑并行、实际串行；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[网络自动化](index.md)聚合页查看更多同类节点。
- [网络 HTTP 请求](http-request.md) (`network.http_request`)。
- [网络上传](upload.md) (`network.upload`)。
- [网络下载](download.md) (`network.download`)。
- [网络响应断言](response-assert.md) (`network.response_assert`)。
- [网络 GraphQL 请求](graphql-request.md) (`network.graphql_request`)。
