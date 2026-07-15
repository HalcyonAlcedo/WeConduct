---
product: weconduct
version: 0.8.1
doc_id: component-group:data-conversion-and-expressions
---

# 转换与表达式

覆盖数据映射、类型转换、表达式和文本替换。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [转换变量类型](convert-value.md) | `data.convert_value` | 将运行时值转换为目标类型，并可选择写回变量。 |
| [计算表达式](evaluate-expression.md) | `data.evaluate_expression` | 计算表达式并得到运行时值。 |
| [数据映射](map.md) | `data.map` | 内置数据映射能力。 |
| [正则替换](regex-replace.md) | `data.regex_replace` | 使用正则表达式替换文本。 |

## 常见组合

可从 `转换变量类型 → 计算表达式 → 数据映射 → 正则替换` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/data-conversion-and-expressions.json" title="转换与表达式节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [转换变量类型](convert-value.md) (`data.convert_value`)：组件库可见。
- [计算表达式](evaluate-expression.md) (`data.evaluate_expression`)：组件库可见。
- [数据映射](map.md) (`data.map`)：组件库可见。
- [正则替换](regex-replace.md) (`data.regex_replace`)：组件库可见。
