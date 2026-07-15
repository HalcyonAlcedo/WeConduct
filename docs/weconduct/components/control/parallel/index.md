---
product: weconduct
version: 0.8.1
doc_id: component-group:control-parallel
---

# 并行控制

覆盖并行分叉与汇合。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [并行汇合](join.md) | `control.join` | 等待一个或多个输入控制分支后再释放下一步。 |
| [并行分叉](parallel-fork.md) | `control.parallel_fork` | 将一个控制令牌分发到多个命名控制分支。 |

## 常见组合

可从 `并行汇合 → 并行分叉` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/control-parallel.json" title="并行控制节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [并行汇合](join.md) (`control.join`)：组件库可见。
- [并行分叉](parallel-fork.md) (`control.parallel_fork`)：组件库可见。
