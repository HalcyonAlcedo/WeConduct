---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:debug-start
---

# 启动 Debug

Debug 使用当前图创建独立会话，并在运行前自动完成准备。UI 不提供单独的 Prepare 按钮。

## 启动前

- 保存或确认当前图草稿正确。
- 主图有且只有一个 `flow.start`。
- 标准运行未占用执行链。
- 需要持久保留的断点和记录帧已写入节点 `debugger` 配置。

## 启动

在 Debug 标签点击启动。后端先准备图与运行环境，再创建会话。活动状态包括 `preparing`、`running`、`paused` 和 `stepping`，这些状态会锁定图编辑。

启动成功但首次同步失败时，会话可能已经存在；刷新活动会话，不要立即重复启动。

Debug 控件见[控制与步进](debug-controls.md)。
