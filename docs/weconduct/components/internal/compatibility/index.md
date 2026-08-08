---
product: weconduct
version: 0.9.0
doc_id: component-group:compatibility-and-internal
---

# 兼容与内部节点

覆盖仅为兼容旧图或内部迁移保留的隐藏节点。


!!! warning 这些节点不在组件库中
    本组的 6 个节点仅用于兼容旧版项目或内部图结构迁移，**不会出现在普通组件库中**，也不能从组件库拖入画布。如果你在旧项目中看到这些节点，说明它们是从早期版本自动迁移过来的。新项目不需要关注这些节点。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [调用蓝图](call-blueprint.md) | `call_blueprint` | 按 blueprint_id 调用可复用组件图。 |
| [结束遍历](end-foreach.md) | `control.end_foreach` | 标记遍历循环体结束。 |
| [遍历中断](foreach-break.md) | `control.foreach_break` | 条件满足时退出当前遍历循环。 |
| [遍历继续](foreach-continue.md) | `control.foreach_continue` | 条件满足时跳过当前遍历项。 |
| [跳转步骤](jump-to-step.md) | `control.jump_to_step` | 跳转到目标步骤。 |
| [调用子图](call-subgraph.md) | `graph.call_subgraph` | 按 subgraph_id 调用可复用子图资源。 |

## 典型搭配

这类节点通常会按 `调用蓝图 → 结束遍历 → 遍历中断 → 遍历继续` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/compatibility-and-internal.json" title="兼容与内部节点节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [调用蓝图](call-blueprint.md) (`call_blueprint`)：兼容/内部（不在组件库中显示）
- [结束遍历](end-foreach.md) (`control.end_foreach`)：兼容/内部（不在组件库中显示）
- [遍历中断](foreach-break.md) (`control.foreach_break`)：兼容/内部（不在组件库中显示）
- [遍历继续](foreach-continue.md) (`control.foreach_continue`)：兼容/内部（不在组件库中显示）
- [跳转步骤](jump-to-step.md) (`control.jump_to_step`)：兼容/内部（不在组件库中显示）
- [调用子图](call-subgraph.md) (`graph.call_subgraph`)：兼容/内部（不在组件库中显示）
