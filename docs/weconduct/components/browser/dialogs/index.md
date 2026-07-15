---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-dialogs
---

# 对话框处理

覆盖对话框监听、处理与代理模式切换。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [处理对话框](handle-dialogs.md) | `dialog.handle_dialogs` | 处理捕获到的浏览器对话框。 |
| [设置对话框代理配置](set-agent-config.md) | `dialog.set_agent_config` | 配置运行时浏览器对话框处理策略。 |
| [切换对话框模式](switch-dialog-mode.md) | `dialog.switch_dialog_mode` | 切换浏览器对话框处理模式。 |
| [监听对话框](watch-dialogs.md) | `dialog.watch_dialogs` | 等待并返回捕获到的浏览器对话框记录。 |

## 典型搭配

这类节点通常会按 `处理对话框 → 设置对话框代理配置 → 切换对话框模式 → 监听对话框` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-dialogs.json" title="对话框处理节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [处理对话框](handle-dialogs.md) (`dialog.handle_dialogs`)
- [设置对话框代理配置](set-agent-config.md) (`dialog.set_agent_config`)
- [切换对话框模式](switch-dialog-mode.md) (`dialog.switch_dialog_mode`)
- [监听对话框](watch-dialogs.md) (`dialog.watch_dialogs`)
