---
product: weconduct
version: 0.9.1
doc_id: weconduct:guide:debug-controls
---

# Debug 控制与步进

控件是否可用由后端会话状态决定：

- **继续**：仅 `paused`。恢复后持续执行，直到下一次断点、手动暂停、异常或结束，不是只执行一步。
- **暂停**：仅 `running` 或 `stepping`。请求在下一个安全暂停点生效，原因记为 `manual_pause`。
- **单步跳过**：仅 `paused`。执行当前层的下一步，不进入组件内部。
- **单步进入**：仅 `paused`。遇到可进入的自定义组件时进入子图。
- **单步跳出**：仅 `paused` 且 `can_step_out = true`，即当前位于组件内部。
- **中止**：`preparing`、`running`、`paused` 或 `stepping` 均可用。

控制请求发送期间按钮会暂时禁用。不要把 `step_requested` 产生的暂停理解为新断点；它是步进控制的预期结果。

中止是 Debug 会话终止，不会自动保存临时断点或变量覆盖。
