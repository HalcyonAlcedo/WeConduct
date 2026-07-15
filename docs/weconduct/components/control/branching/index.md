---
product: weconduct
version: 0.8.1
doc_id: component-group:control-branching
---

# 分支控制

覆盖条件判断与多路分支。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [条件分支](if.md) | `control.if` | 根据布尔条件分支控制流。 |
| [多路分支](switch.md) | `control.switch` | 按输入值匹配选择控制分支。 |

## 典型搭配

这类节点通常会按 `条件分支 → 多路分支` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/control-branching.json" title="分支控制节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [条件分支](if.md) (`control.if`)
- [多路分支](switch.md) (`control.switch`)
