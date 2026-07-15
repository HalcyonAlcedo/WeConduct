---
product: weave
version: 0.5.0
stable: true
doc_id: weave:guide:browser-storage
---

# 浏览器存储

## 三个标签页

“存储管理”面板有三个页签：

- `Local Storage`
- `Session Storage`
- `Cookies`

没有会话时会提示“启动会话后可查看页面存储”。

## Local Storage / Session Storage

这两个页签支持：

- 筛选 Key 或 Value
- `+ 新增`
- `🔄 刷新`
- 双击 Key 或 Value 进入编辑
- 点击行尾 `✕` 删除

如果某个值是合法 JSON，表格里会显示 `JSON` 标记。

## Cookies

Cookies 页签当前支持：

- 查看名称、值、域、路径、过期时间、HttpOnly
- 删除单条 Cookie

## 0.5.0 的界面边界

虽然后端提供了这些接口：

- 清空全部 Local Storage
- 清空全部 Session Storage
- 写入 Cookie

但 0.5.0 内置“存储管理”面板没有对应按钮。也就是说：

- 你可以在 UI 里新增和编辑 Local / Session Storage。
- 你可以在 UI 里删除 Cookie。
- 你不能在当前内置 UI 里直接新增 Cookie，也不能一键清空全部存储。

## 与其他工具配合

如果你要把登录态带给别的工具，最实用的做法是从这里人工抄录：

- 关键 Cookie
- Local Storage 中的 token
- Session Storage 中的会话键值
