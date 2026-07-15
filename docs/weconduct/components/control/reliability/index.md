---
product: weconduct
version: 0.8.1
doc_id: component-group:control-reliability
---

# 可靠性控制

覆盖重试与故障切换。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [故障切换](failover.md) | `control.failover` | 主路径失败时切换到备用分支。 |
| [重试](retry.md) | `control.retry` | 重试下游分支直到成功或尝试次数耗尽。 |

## 常见组合

可从 `故障切换 → 重试` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/control-reliability.json" title="可靠性控制节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [故障切换](failover.md) (`control.failover`)：组件库可见。
- [重试](retry.md) (`control.retry`)：组件库可见。
