---
product: weconduct
version: 0.9.1
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

如果项目包含加密初始参数，Debug 启动会先返回 `unlock_required` 并弹出项目密码窗口。密码验证成功后才启动 Debug worker；错误密码只产生诊断，不会创建可执行的敏感值副本。终止 Debug 会话会关闭仍打开的解锁窗口。

Debug 启动准备、图校验或编译失败时，错误会进入诊断面板并保留节点/边引用，不能只显示“会话未创建”。对图上的节点或边进行修改，或再次校验/编译后，旧的对象高亮会被清理；诊断列表仍以当前有效条目为准。

启动成功但首次同步失败时，会话可能已经存在；刷新活动会话，不要立即重复启动。

Debug 控件见[控制与步进](debug-controls.md)。
