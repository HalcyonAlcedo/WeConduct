---
product: weconduct
version: 0.8.1
doc_id: weconduct:reference:keyboard-shortcuts
---

# 键盘快捷键

以下按 0.8.1 实际注册行为整理。

| 快捷键 | 行为 | 条件 |
|---|---|---|
| `Ctrl+Enter` | 启动标准运行 | 图非空，且没有活动运行或 Debug |
| `Ctrl+Z` | 撤销图编辑 | 当前图存在 |
| `Ctrl+Y` | 重做图编辑 | 当前图存在 |
| `Ctrl+C` | 复制选中节点 | 没有文本选区，焦点不在输入控件 |
| `Ctrl+V` | 粘贴节点 | 已复制节点，焦点不在输入控件 |
| `Delete` | 删除选中节点 | 按 `confirm_delete_node` 决定是否确认 |
| `Ctrl+B` | 打开组件库 | 全局 |
| `Ctrl+E` | 打开源输入 | 全局 |
| `Ctrl+K` | 清空源输入 | 焦点不在输入控件 |
| `Ctrl+S` | 显示“请使用 文件 → 保存”提示 | 0.8.1 不直接执行保存 |

## 当前限制

帮助窗口显示 `Ctrl+O` 和 `Ctrl+N`，但 0.8.1 全局快捷键注册中没有对应打开项目或新建项目处理器。请使用 **文件** 菜单。

Debug 变量的普通输入框按 `Enter` 提交；对象和数组编辑框使用 `Ctrl+Enter` 提交。历史变量和历史快照只读。
