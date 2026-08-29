---
product: weconduct
version: 0.9.1
doc_id: component-group:flow-and-components
---

# 流程与组件边界

覆盖流程入口与组件输入输出边界。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [组件输入](input.md) | `component.input` | 在自定义节点图中声明正式组件输入边界。 |
| [组件输出](output.md) | `component.output` | 在自定义节点图中声明正式组件输出边界。 |
| [开始](start.md) | `flow.start` | 声明流程入口和初始变量。 |

## 典型搭配

这类节点通常会按 `组件输入 → 组件输出 → 开始` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/flow-and-components.json" title="流程与组件边界节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [组件输入](input.md) (`component.input`)
- [组件输出](output.md) (`component.output`)
- [开始](start.md) (`flow.start`)
