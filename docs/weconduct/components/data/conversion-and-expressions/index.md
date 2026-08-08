---
product: weconduct
version: 0.9.0
doc_id: component-group:data-conversion-and-expressions
---

# 转换与表达式

覆盖数据映射、类型转换、表达式和文本替换。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [转换变量类型](convert-value.md) | `data.convert_value` | 将运行时值转换为目标类型，并可选择写回变量。 |
| [计算表达式](evaluate-expression.md) | `data.evaluate_expression` | 计算表达式并得到运行时值。 |
| [数据映射](map.md) | `data.map` | 内置数据映射能力。 |
| [正则替换](regex-replace.md) | `data.regex_replace` | 使用正则表达式替换文本。 |

## 典型搭配

这类节点通常会按 `转换变量类型 → 计算表达式 → 数据映射 → 正则替换` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/data-conversion-and-expressions.json" title="转换与表达式节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [转换变量类型](convert-value.md) (`data.convert_value`)
- [计算表达式](evaluate-expression.md) (`data.evaluate_expression`)
- [数据映射](map.md) (`data.map`)
- [正则替换](regex-replace.md) (`data.regex_replace`)
