---
product: weave
version: 0.5.0
stable: true
doc_id: weave:index
---

# Weave 0.5.0

Weave 是一个独立的浏览器分析工具。它能让你实时查看网页的 DOM 结构、元素选择器、网络请求和浏览器存储状态，帮你快速定位页面元素和调试自动化流程。

## Weave 和 WeConduct 的关系

Weave 可以和 WeConduct 配合使用，但两个工具之间目前没有直接的同步接口。一个典型的工作流是：

1. 在 WeConduct 中打开一个浏览器页面进行自动化操作。
2. 切换到 Weave，查看页面的 DOM 树，找到目标元素的精确选择器。
3. 把选择器复制回 WeConduct，用于配置浏览器节点的选择器参数。

这种配合方式在定位复杂页面元素时非常有用。

## 主要功能

- **页面分析**：实时查看页面的 DOM 树结构，搜索和筛选元素
- **元素检查**：查看每个元素的属性、样式和精确的 CSS 选择器
- **网络监控**：捕获和查看页面的网络请求与响应
- **存储管理**：查看和修改 Cookie、Local Storage、Session Storage
- **拦截规则**：设置请求拦截和修改规则

## 快速导航

- [安装与更新](getting-started/install-and-update.md)
- [工作区](guide/workspaces.md) — 管理工作空间和项目
- [浏览器会话](guide/browser-sessions.md) — 建立和切换浏览器连接
- [页面树与搜索](guide/page-tree-and-search.md) — 浏览和分析页面 DOM
- [节点详情与选择器](guide/node-details-and-selectors.md) — 获取精确的元素选择器
- [网络捕获与重放](guide/network-capture-and-replay.md) — 监控网络流量
- [与 WeConduct 配合使用](workflows/use-with-weconduct.md) — 两个工具的协作方式
- [故障排查](troubleshooting/index.md)

## 版本说明

Weave 目前处于 0.5.0 版本，部分功能仍在完善中。如果你发现某些操作没有内置的 UI 入口（比如直接在面板中新增 Cookie、重放网络请求等），这些功能可能会在后续版本中加入。当前可以通过手动操作或结合其他工具来实现。
