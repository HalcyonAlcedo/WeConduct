---
product: weconduct
version: 0.9.0
doc_id: component-group:browser-state-and-content
---

# 页面状态与内容

覆盖截图、识别、存在性检查与页面内容读取。

## 节点速览

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

## 典型搭配

这类节点通常会按 `元素截图 → 元素存在 → 读取 HTML → 读取内部 HTML` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-state-and-content.json" title="页面状态与内容节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [元素截图](element-screenshot.md) (`browser.element_screenshot`)
- [元素存在](exists.md) (`browser.exists`)
- [读取 HTML](get-html.md) (`browser.get_html`)
- [读取内部 HTML](get-inner-html.md) (`browser.get_inner_html`)
- [元素已勾选](is-checked.md) (`browser.is_checked`)
- [元素可用](is-enabled.md) (`browser.is_enabled`)
- [元素可见](is-visible.md) (`browser.is_visible`)
- [识别验证码](recognize-captcha.md) (`browser.recognize_captcha`)
- [截图](screenshot.md) (`browser.screenshot`)
