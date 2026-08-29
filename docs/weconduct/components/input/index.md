---
product: weconduct
version: 0.9.1
doc_id: component-group:input-and-messaging
---

# 输入与消息

覆盖运行时待输入和运行/Debug 消息发布。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [请求输入](input-request.md) | `input.request` | 暂停执行会话，等待多字段表单提交、超时或取消。 |
| [消息](message-emit.md) | `message.emit` | 将配置消息写入运行诊断。 |

## 典型搭配

这类节点通常会按 `请求输入 → 消息` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../assets/graphs/components/groups/input-and-messaging.json" title="输入与消息节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [请求输入](input-request.md) (`input.request`)
- [消息](message-emit.md) (`message.emit`)
