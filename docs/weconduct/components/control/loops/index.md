---
product: weconduct
version: 0.8.1
doc_id: component-group:control-loops
---

# 循环控制

覆盖遍历与条件循环。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [遍历](foreach.md) | `control.foreach` | 遍历列表项。 |
| [条件循环](while.md) | `control.while` | 当条件保持为真时重复控制分支。 |

## 常见组合

可从 `遍历 → 条件循环` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/control-loops.json" title="循环控制节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [遍历](foreach.md) (`control.foreach`)：组件库可见。
- [条件循环](while.md) (`control.while`)：组件库可见。
