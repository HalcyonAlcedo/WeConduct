---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-navigation
---

# 页面导航

覆盖页面跳转、刷新与标签切换。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [关闭标签页](close-tab.md) | `browser.close_tab` | 关闭浏览器标签页。 |
| [后退](go-back.md) | `browser.go_back` | 浏览器历史后退。 |
| [前进](go-forward.md) | `browser.go_forward` | 浏览器历史前进。 |
| [导航](navigate.md) | `browser.navigate` | 导航浏览器到目标 URL。 |
| [打开标签页](open-tab.md) | `browser.open_tab` | 打开新的浏览器标签页。 |
| [刷新](refresh.md) | `browser.refresh` | 刷新当前浏览器页面。 |
| [无缓存刷新](refresh-no-cache.md) | `browser.refresh_no_cache` | 无缓存刷新当前浏览器页面。 |
| [切换标签页](switch-tab.md) | `browser.switch_tab` | 切换到另一个浏览器标签页。 |
| [等待 URL 变化](wait-for-url-change.md) | `browser.wait_for_url_change` | 等待当前页面 URL 发生变化并可选匹配指定模式。 |

## 常见组合

可从 `关闭标签页 → 后退 → 前进 → 导航` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-navigation.json" title="页面导航节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [关闭标签页](close-tab.md) (`browser.close_tab`)：组件库可见。
- [后退](go-back.md) (`browser.go_back`)：组件库可见。
- [前进](go-forward.md) (`browser.go_forward`)：组件库可见。
- [导航](navigate.md) (`browser.navigate`)：组件库可见。
- [打开标签页](open-tab.md) (`browser.open_tab`)：组件库可见。
- [刷新](refresh.md) (`browser.refresh`)：组件库可见。
- [无缓存刷新](refresh-no-cache.md) (`browser.refresh_no_cache`)：组件库可见。
- [切换标签页](switch-tab.md) (`browser.switch_tab`)：组件库可见。
- [等待 URL 变化](wait-for-url-change.md) (`browser.wait_for_url_change`)：组件库可见。
