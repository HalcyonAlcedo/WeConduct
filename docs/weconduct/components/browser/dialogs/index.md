---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-dialogs
---

# 对话框处理

覆盖对话框监听、处理与代理模式切换。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [处理对话框](handle-dialogs.md) | `dialog.handle_dialogs` | 处理捕获到的浏览器对话框。 |
| [设置对话框代理配置](set-agent-config.md) | `dialog.set_agent_config` | 配置运行时浏览器对话框处理策略。 |
| [切换对话框模式](switch-dialog-mode.md) | `dialog.switch_dialog_mode` | 切换浏览器对话框处理模式。 |
| [监听对话框](watch-dialogs.md) | `dialog.watch_dialogs` | 等待并返回捕获到的浏览器对话框记录。 |

## 常见组合

可从 `处理对话框 → 设置对话框代理配置 → 切换对话框模式 → 监听对话框` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-dialogs.json" title="对话框处理节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [处理对话框](handle-dialogs.md) (`dialog.handle_dialogs`)：组件库可见。
- [设置对话框代理配置](set-agent-config.md) (`dialog.set_agent_config`)：组件库可见。
- [切换对话框模式](switch-dialog-mode.md) (`dialog.switch_dialog_mode`)：组件库可见。
- [监听对话框](watch-dialogs.md) (`dialog.watch_dialogs`)：组件库可见。
