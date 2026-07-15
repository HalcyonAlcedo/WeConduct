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

## 0.5.0 暂不支持的操作

当前版本的内置面板还不能执行以下操作：

- 新增 Cookie（可以查看和删除，但不能创建）
- 一键清空全部 Local Storage 或 Session Storage

如果需要这些操作，可以切换到 WeConduct 使用对应的浏览器存储节点来完成。

## 与其他工具配合

如果你要把登录态带给别的工具，最实用的做法是从这里人工抄录：

- 关键 Cookie
- Local Storage 中的 token
- Session Storage 中的会话键值
