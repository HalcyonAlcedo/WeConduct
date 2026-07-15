---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-state-and-content
---

# 页面状态与内容

覆盖截图、识别、存在性检查与页面内容读取。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [元素截图](element-screenshot.md) | `browser.element_screenshot` | 截取目标元素的截图。 |
| [元素存在](exists.md) | `browser.exists` | 检查当前页面上是否存在指定选择器。 |
| [读取 HTML](get-html.md) | `browser.get_html` | 读取目标元素的 outer HTML。 |
| [读取内部 HTML](get-inner-html.md) | `browser.get_inner_html` | 读取目标元素的 inner HTML。 |
| [元素已勾选](is-checked.md) | `browser.is_checked` | 检查当前页面上指定选择器是否已勾选。 |
| [元素可用](is-enabled.md) | `browser.is_enabled` | 检查当前页面上指定选择器是否可用。 |
| [元素可见](is-visible.md) | `browser.is_visible` | 检查当前页面上指定选择器是否可见。 |
| [识别验证码](recognize-captcha.md) | `browser.recognize_captcha` | 使用 captcha_ocr 识别验证码图片。 |
| [截图](screenshot.md) | `browser.screenshot` | 截取浏览器截图。 |

## 常见组合

可从 `元素截图 → 元素存在 → 读取 HTML → 读取内部 HTML` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-state-and-content.json" title="页面状态与内容节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [元素截图](element-screenshot.md) (`browser.element_screenshot`)：组件库可见。
- [元素存在](exists.md) (`browser.exists`)：组件库可见。
- [读取 HTML](get-html.md) (`browser.get_html`)：组件库可见。
- [读取内部 HTML](get-inner-html.md) (`browser.get_inner_html`)：组件库可见。
- [元素已勾选](is-checked.md) (`browser.is_checked`)：组件库可见。
- [元素可用](is-enabled.md) (`browser.is_enabled`)：组件库可见。
- [元素可见](is-visible.md) (`browser.is_visible`)：组件库可见。
- [识别验证码](recognize-captcha.md) (`browser.recognize_captcha`)：组件库可见。
- [截图](screenshot.md) (`browser.screenshot`)：组件库可见。
