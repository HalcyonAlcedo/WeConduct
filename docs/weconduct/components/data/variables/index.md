---
product: weconduct
version: 0.9.0
doc_id: component-group:data-variables
---

# 变量读写

覆盖变量映射、读写与数值增减。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [变量递减](decrement-variable.md) | `data.decrement_variable` | 递减数值型运行时变量。 |
| [读取变量](get-variable.md) | `data.get_variable` | 读取运行时变量。 |
| [变量递增](increment-variable.md) | `data.increment_variable` | 递增数值型运行时变量。 |
| [写入变量](set-variable.md) | `data.set_variable` | 写入运行时变量。 |
| [批量写入变量](set-variables-batch.md) | `data.set_variables_batch` | 一次写入多个运行时变量。 |

## 典型搭配

这类节点通常会按 `变量递减 → 读取变量 → 变量递增 → 写入变量` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/data-variables.json" title="变量读写节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [变量递减](decrement-variable.md) (`data.decrement_variable`)
- [读取变量](get-variable.md) (`data.get_variable`)
- [变量递增](increment-variable.md) (`data.increment_variable`)
- [写入变量](set-variable.md) (`data.set_variable`)
- [批量写入变量](set-variables-batch.md) (`data.set_variables_batch`)
