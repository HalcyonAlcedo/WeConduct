---
product: weconduct
version: 0.9.0
doc_id: component-group:browser-waits
---

# 等待条件

覆盖元素、导航、文本和值等等待条件。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [等待属性](wait-for-attribute.md) | `browser.wait_for_attribute` | 等待元素属性匹配预期值。 |
| [等待元素](wait-for-element.md) | `browser.wait_for_element` | 等待目标元素出现。 |
| [等待导航](wait-for-navigation.md) | `browser.wait_for_navigation` | 等待浏览器导航完成。 |
| [等待弹窗](wait-for-popup.md) | `browser.wait_for_popup` | 等待弹出窗口或新页面打开。 |
| [等待文本](wait-for-text.md) | `browser.wait_for_text` | 等待元素文本匹配预期值。 |
| [等待超时](wait-for-timeout.md) | `browser.wait_for_timeout` | 按固定时长等待。 |
| [等待值](wait-for-value.md) | `browser.wait_for_value` | 等待输入框或元素值匹配预期值。 |

## 典型搭配

这类节点通常会按 `等待属性 → 等待元素 → 等待导航 → 等待弹窗` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-waits.json" title="等待条件节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [等待属性](wait-for-attribute.md) (`browser.wait_for_attribute`)
- [等待元素](wait-for-element.md) (`browser.wait_for_element`)
- [等待导航](wait-for-navigation.md) (`browser.wait_for_navigation`)
- [等待弹窗](wait-for-popup.md) (`browser.wait_for_popup`)
- [等待文本](wait-for-text.md) (`browser.wait_for_text`)
- [等待超时](wait-for-timeout.md) (`browser.wait_for_timeout`)
- [等待值](wait-for-value.md) (`browser.wait_for_value`)
