---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-navigation
---

# 页面导航

覆盖页面跳转、刷新与标签切换。

## 节点速览

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

## 典型搭配

这类节点通常会按 `关闭标签页 → 后退 → 前进 → 导航` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-navigation.json" title="页面导航节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [关闭标签页](close-tab.md) (`browser.close_tab`)
- [后退](go-back.md) (`browser.go_back`)
- [前进](go-forward.md) (`browser.go_forward`)
- [导航](navigate.md) (`browser.navigate`)
- [打开标签页](open-tab.md) (`browser.open_tab`)
- [刷新](refresh.md) (`browser.refresh`)
- [无缓存刷新](refresh-no-cache.md) (`browser.refresh_no_cache`)
- [切换标签页](switch-tab.md) (`browser.switch_tab`)
- [等待 URL 变化](wait-for-url-change.md) (`browser.wait_for_url_change`)
