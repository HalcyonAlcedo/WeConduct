---
product: weconduct
version: 0.8.1
doc_id: component-group:compatibility-and-internal
---

# 兼容与内部节点

覆盖仅为兼容旧图或内部迁移保留的隐藏节点。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [调用蓝图](call-blueprint.md) | `call_blueprint` | 按 blueprint_id 调用可复用组件图。 |
| [结束遍历](end-foreach.md) | `control.end_foreach` | 标记遍历循环体结束。 |
| [遍历中断](foreach-break.md) | `control.foreach_break` | 条件满足时退出当前遍历循环。 |
| [遍历继续](foreach-continue.md) | `control.foreach_continue` | 条件满足时跳过当前遍历项。 |
| [跳转步骤](jump-to-step.md) | `control.jump_to_step` | 跳转到目标步骤。 |
| [调用子图](call-subgraph.md) | `graph.call_subgraph` | 按 subgraph_id 调用可复用子图资源。 |

## 常见组合

可从 `调用蓝图 → 结束遍历 → 遍历中断 → 遍历继续` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/compatibility-and-internal.json" title="兼容与内部节点节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [调用蓝图](call-blueprint.md) (`call_blueprint`)：兼容/内部。
- [结束遍历](end-foreach.md) (`control.end_foreach`)：兼容/内部。
- [遍历中断](foreach-break.md) (`control.foreach_break`)：兼容/内部。
- [遍历继续](foreach-continue.md) (`control.foreach_continue`)：兼容/内部。
- [跳转步骤](jump-to-step.md) (`control.jump_to_step`)：兼容/内部。
- [调用子图](call-subgraph.md) (`graph.call_subgraph`)：兼容/内部。
