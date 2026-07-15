---
product: weconduct
version: 0.8.1
doc_id: component-group:data-variables
---

# 变量读写

覆盖变量映射、读写与数值增减。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [变量递减](decrement-variable.md) | `data.decrement_variable` | 递减数值型运行时变量。 |
| [读取变量](get-variable.md) | `data.get_variable` | 读取运行时变量。 |
| [变量递增](increment-variable.md) | `data.increment_variable` | 递增数值型运行时变量。 |
| [写入变量](set-variable.md) | `data.set_variable` | 写入运行时变量。 |
| [批量写入变量](set-variables-batch.md) | `data.set_variables_batch` | 一次写入多个运行时变量。 |

## 常见组合

可从 `变量递减 → 读取变量 → 变量递增 → 写入变量` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/data-variables.json" title="变量读写节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [变量递减](decrement-variable.md) (`data.decrement_variable`)：组件库可见。
- [读取变量](get-variable.md) (`data.get_variable`)：组件库可见。
- [变量递增](increment-variable.md) (`data.increment_variable`)：组件库可见。
- [写入变量](set-variable.md) (`data.set_variable`)：组件库可见。
- [批量写入变量](set-variables-batch.md) (`data.set_variables_batch`)：组件库可见。
