---
product: weave
version: 0.5.0
stable: true
doc_id: weave:index
---

# Weave 0.5.0

Weave 是独立桌面软件，用来查看页面结构、运行时选中状态、网络请求和浏览器存储。它可以和 WeConduct 配合，但 0.5.0 只有手工协作，没有直接同步接口。

## 从这里开始

- [安装与更新](getting-started/install-and-update.md)
- [工作区](guide/workspaces.md)
- [浏览器会话](guide/browser-sessions.md)
- [页面树与搜索](guide/page-tree-and-search.md)
- [节点详情与选择器](guide/node-details-and-selectors.md)
- [叠加层与检查模式](guide/overlay-and-inspect-mode.md)
- [网络捕获与重放](guide/network-capture-and-replay.md)
- [拦截规则](guide/intercept-rules.md)
- [浏览器存储](guide/browser-storage.md)
- [布局与设置](guide/layout-and-settings.md)
- [插件](guide/plugins.md)
- [与 WeConduct 配合](workflows/use-with-weconduct.md)
- [故障排查](troubleshooting/index.md)

## 产品边界

- Weave 0.5.0 自带十个内置面板：工作区、页面树、会话控制、节点详情、搜索、叠加层、设置、网络捕获、存储管理、拦截规则。
- 工作区、设置、布局、会话快照都保存在 `Weave.exe` 同目录的 `.weave\` 下。
- 插件目录固定为 `Weave.exe` 同目录的 `plugins\`。
- 与 WeConduct 的配合方式是人工复制选择器、请求数据、Cookie 或存储值，不存在自动导入、共享工作区或联动调试接口。
