---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-interaction
---

# 页面交互

覆盖点击、输入、选择、拖放和滚动等交互动作。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [勾选](check.md) | `browser.check` | 在浏览器中勾选复选框或单选框。 |
| [点击](click.md) | `browser.click` | 点击浏览器中的目标元素。 |
| [拖放](drag-and-drop.md) | `browser.drag_and_drop` | 拖动元素并将其放到另一个元素上。 |
| [填入](fill.md) | `browser.fill` | 向浏览器输入框填入内容。 |
| [快捷键](hotkey.md) | `browser.hotkey` | 在当前页面或目标元素上触发快捷键。 |
| [悬停](hover.md) | `browser.hover` | 将鼠标悬停在目标元素上。 |
| [键盘输入](keyboard-type.md) | `browser.keyboard_type` | 使用浏览器键盘输入文本。 |
| [按键](press-key.md) | `browser.press_key` | 在当前页面或目标元素上按下键盘按键。 |
| [滚动页面](scroll-page.md) | `browser.scroll_page` | 按偏移量或绝对位置滚动当前页面。 |
| [滚动到元素](scroll-to-element.md) | `browser.scroll_to_element` | 滚动页面直到目标元素进入视野。 |
| [选择选项](select-option.md) | `browser.select_option` | 在浏览器中选择目标选项。 |
| [设置上传文件](set-input-files.md) | `browser.set_input_files` | 向浏览器文件输入框附加本地文件路径。 |
| [取消勾选](uncheck.md) | `browser.uncheck` | 在浏览器中取消勾选复选框。 |

## 常见组合

可从 `勾选 → 点击 → 拖放 → 填入` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-interaction.json" title="页面交互节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [勾选](check.md) (`browser.check`)：组件库可见。
- [点击](click.md) (`browser.click`)：组件库可见。
- [拖放](drag-and-drop.md) (`browser.drag_and_drop`)：组件库可见。
- [填入](fill.md) (`browser.fill`)：组件库可见。
- [快捷键](hotkey.md) (`browser.hotkey`)：组件库可见。
- [悬停](hover.md) (`browser.hover`)：组件库可见。
- [键盘输入](keyboard-type.md) (`browser.keyboard_type`)：组件库可见。
- [按键](press-key.md) (`browser.press_key`)：组件库可见。
- [滚动页面](scroll-page.md) (`browser.scroll_page`)：组件库可见。
- [滚动到元素](scroll-to-element.md) (`browser.scroll_to_element`)：组件库可见。
- [选择选项](select-option.md) (`browser.select_option`)：组件库可见。
- [设置上传文件](set-input-files.md) (`browser.set_input_files`)：组件库可见。
- [取消勾选](uncheck.md) (`browser.uncheck`)：组件库可见。
