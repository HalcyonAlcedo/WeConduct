---
product: weconduct
version: 0.8.1
doc_id: component-group:data-page-values
---

# 页面取值

覆盖文本、属性、值与元素数量读取。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [读取属性](get-attribute.md) | `data.get_attribute` | 读取浏览器元素属性到运行时变量。 |
| [读取元素数量](get-element-count.md) | `data.get_element_count` | 统计匹配选择器的浏览器元素数量。 |
| [读取文本](get-text.md) | `data.get_text` | 读取浏览器元素文本到运行时变量。 |
| [读取值](get-value.md) | `data.get_value` | 读取浏览器输入值到运行时变量。 |

## 常见组合

可从 `读取属性 → 读取元素数量 → 读取文本 → 读取值` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/data-page-values.json" title="页面取值节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [读取属性](get-attribute.md) (`data.get_attribute`)：组件库可见。
- [读取元素数量](get-element-count.md) (`data.get_element_count`)：组件库可见。
- [读取文本](get-text.md) (`data.get_text`)：组件库可见。
- [读取值](get-value.md) (`data.get_value`)：组件库可见。
