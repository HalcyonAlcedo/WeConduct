---
product: weconduct
version: 0.9.0
doc_id: component-group:network-automation
---

# 网络自动化

覆盖 HTTP、GraphQL、SSE、WebSocket、上传、下载、断言和批量请求。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [网络批量请求](batch-request.md) | `network.batch_request` | 以有界并发执行并按输入顺序返回网络请求。 |
| [网络下载](download.md) | `network.download` | 将响应下载到会话级临时存储。 |
| [网络 GraphQL 请求](graphql-request.md) | `network.graphql_request` | 通过网络运行时执行 GraphQL 查询或变更。 |
| [网络 HTTP 请求](http-request.md) | `network.http_request` | 通过会话级网络运行时执行 HTTP 请求。 |
| [网络响应断言](response-assert.md) | `network.response_assert` | 使用结构化断言验证网络响应。 |
| [网络 SSE 连接](sse-connect.md) | `network.sse_connect` | 连接会话级 SSE 流并拉取事件。 |
| [网络上传](upload.md) | `network.upload` | 通过会话级网络运行时流式上传受控本地文件。 |
| [网络 WebSocket 连接](websocket-connect.md) | `network.websocket_connect` | 连接并操作会话级 WebSocket。 |

## 典型搭配

这类节点通常会按 `网络批量请求 → 网络下载 → 网络 GraphQL 请求 → 网络 HTTP 请求` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../assets/graphs/components/groups/network-automation.json" title="网络自动化节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [网络批量请求](batch-request.md) (`network.batch_request`)
- [网络下载](download.md) (`network.download`)
- [网络 GraphQL 请求](graphql-request.md) (`network.graphql_request`)
- [网络 HTTP 请求](http-request.md) (`network.http_request`)
- [网络响应断言](response-assert.md) (`network.response_assert`)
- [网络 SSE 连接](sse-connect.md) (`network.sse_connect`)
- [网络上传](upload.md) (`network.upload`)
- [网络 WebSocket 连接](websocket-connect.md) (`network.websocket_connect`)
