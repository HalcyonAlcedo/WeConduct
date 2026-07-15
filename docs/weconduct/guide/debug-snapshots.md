---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:debug-snapshots
---

# Debug 快照

打开 Debug 工具栏中的 **快照** 窗口查看关键帧。默认显示三类事件：

- `breakpoint.hit`：断点命中。
- `debug.paused`：手动暂停、步进、异常或其他暂停。
- `record_frame.hit`：记录帧命中，不中断执行。

## 快照内容

快照保存事件序号、时间、节点、暂停时机、原因、`frame_identity`、实例路径、迭代栈、变量快照、变量描述和变更信息。后端在写入关键事件时冻结这些数据，历史读取不会跟随当前变量变化。

## 追溯

同一节点在循环或组件中可多次命中。结构化界面可直接查看 `event_index`、`frame_identity`、`event_id` 和 `keyframe_id`；断点或记录帧的 `breakpoint_ordinal`、`record_frame_ordinal` 命中序号需要展开原始 JSON。追溯时不要只看节点名。

手动暂停的 `reason` 为 `manual_pause`。记录帧的 `pause_requested` 为 `false`。选择历史会话或历史投影后，变量和快照均只读。

原始 JSON 只用于深度排查；日常查看应使用字段分组和变量表。
