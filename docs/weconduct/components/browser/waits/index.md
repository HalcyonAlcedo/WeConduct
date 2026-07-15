---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-waits
---

# 等待条件

覆盖元素、导航、文本和值等等待条件。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [等待属性](wait-for-attribute.md) | `browser.wait_for_attribute` | 等待元素属性匹配预期值。 |
| [等待元素](wait-for-element.md) | `browser.wait_for_element` | 等待目标元素出现。 |
| [等待导航](wait-for-navigation.md) | `browser.wait_for_navigation` | 等待浏览器导航完成。 |
| [等待弹窗](wait-for-popup.md) | `browser.wait_for_popup` | 等待弹出窗口或新页面打开。 |
| [等待文本](wait-for-text.md) | `browser.wait_for_text` | 等待元素文本匹配预期值。 |
| [等待超时](wait-for-timeout.md) | `browser.wait_for_timeout` | 按固定时长等待。 |
| [等待值](wait-for-value.md) | `browser.wait_for_value` | 等待输入框或元素值匹配预期值。 |

## 常见组合

可从 `等待属性 → 等待元素 → 等待导航 → 等待弹窗` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-waits.json" title="等待条件节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [等待属性](wait-for-attribute.md) (`browser.wait_for_attribute`)：组件库可见。
- [等待元素](wait-for-element.md) (`browser.wait_for_element`)：组件库可见。
- [等待导航](wait-for-navigation.md) (`browser.wait_for_navigation`)：组件库可见。
- [等待弹窗](wait-for-popup.md) (`browser.wait_for_popup`)：组件库可见。
- [等待文本](wait-for-text.md) (`browser.wait_for_text`)：组件库可见。
- [等待超时](wait-for-timeout.md) (`browser.wait_for_timeout`)：组件库可见。
- [等待值](wait-for-value.md) (`browser.wait_for_value`)：组件库可见。
