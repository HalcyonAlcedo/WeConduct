---
product: weconduct
version: 0.8.1
doc_id: component-group:control-reliability
---

# 可靠性控制

覆盖重试与故障切换。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [故障切换](failover.md) | `control.failover` | 主路径失败时切换到备用分支。 |
| [重试](retry.md) | `control.retry` | 重试下游分支直到成功或尝试次数耗尽。 |

## 典型搭配

这类节点通常会按 `故障切换 → 重试` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/control-reliability.json" title="可靠性控制节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [故障切换](failover.md) (`control.failover`)
- [重试](retry.md) (`control.retry`)
