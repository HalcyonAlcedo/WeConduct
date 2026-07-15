---
product: weconduct
version: 0.8.1
doc_id: component-group:control-loops
---

# 循环控制

覆盖遍历与条件循环。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [遍历](foreach.md) | `control.foreach` | 遍历列表项。 |
| [条件循环](while.md) | `control.while` | 当条件保持为真时重复控制分支。 |

## 典型搭配

这类节点通常会按 `遍历 → 条件循环` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/control-loops.json" title="循环控制节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [遍历](foreach.md) (`control.foreach`)
- [条件循环](while.md) (`control.while`)
