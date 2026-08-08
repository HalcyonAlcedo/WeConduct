---
product: weconduct
version: 0.9.0
doc_id: component-group:data-page-values
---

# 页面取值

覆盖文本、属性、值与元素数量读取。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [读取属性](get-attribute.md) | `data.get_attribute` | 读取浏览器元素属性到运行时变量。 |
| [读取元素数量](get-element-count.md) | `data.get_element_count` | 统计匹配选择器的浏览器元素数量。 |
| [读取文本](get-text.md) | `data.get_text` | 读取浏览器元素文本到运行时变量。 |
| [读取值](get-value.md) | `data.get_value` | 读取浏览器输入值到运行时变量。 |

## 典型搭配

这类节点通常会按 `读取属性 → 读取元素数量 → 读取文本 → 读取值` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/data-page-values.json" title="页面取值节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [读取属性](get-attribute.md) (`data.get_attribute`)
- [读取元素数量](get-element-count.md) (`data.get_element_count`)
- [读取文本](get-text.md) (`data.get_text`)
- [读取值](get-value.md) (`data.get_value`)
