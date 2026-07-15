---
product: weconduct
version: 0.8.1
doc_id: component-group:flow-and-components
---

# 流程与组件边界

覆盖流程入口与组件输入输出边界。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [组件输入](input.md) | `component.input` | 在自定义节点图中声明正式组件输入边界。 |
| [组件输出](output.md) | `component.output` | 在自定义节点图中声明正式组件输出边界。 |
| [开始](start.md) | `flow.start` | 声明流程入口和初始变量。 |

## 常见组合

可从 `组件输入 → 组件输出 → 开始` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/flow-and-components.json" title="流程与组件边界节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [组件输入](input.md) (`component.input`)：组件库可见。
- [组件输出](output.md) (`component.output`)：组件库可见。
- [开始](start.md) (`flow.start`)：组件库可见。
