---
product: weconduct
version: 0.9.0
doc_id: component-group:control-parallel
---

# 并行控制

覆盖并行分叉与汇合。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [并行汇合](join.md) | `control.join` | 等待一个或多个输入控制分支后再释放下一步。 |
| [并行分叉](parallel-fork.md) | `control.parallel_fork` | 将一个控制令牌分发到多个命名控制分支。 |

## 典型搭配

这类节点通常会按 `并行汇合 → 并行分叉` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/control-parallel.json" title="并行控制节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [并行汇合](join.md) (`control.join`)
- [并行分叉](parallel-fork.md) (`control.parallel_fork`)
