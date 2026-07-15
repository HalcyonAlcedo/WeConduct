---
product: weconduct
version: 0.8.1
doc_id: component-group:control-branching
---

# 分支控制

覆盖条件判断与多路分支。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [条件分支](if.md) | `control.if` | 根据布尔条件分支控制流。 |
| [多路分支](switch.md) | `control.switch` | 按输入值匹配选择控制分支。 |

## 常见组合

可从 `条件分支 → 多路分支` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/control-branching.json" title="分支控制节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [条件分支](if.md) (`control.if`)：组件库可见。
- [多路分支](switch.md) (`control.switch`)：组件库可见。
