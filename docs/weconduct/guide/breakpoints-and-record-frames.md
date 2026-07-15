---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:breakpoints-record-frames
---

# 断点与记录帧

<weconduct-graph src="../../assets/graphs/debug/breakpoint-record-frame.json" title="执行前断点与记录帧">图示加载失败时：写入计数节点有执行前断点，读取计数节点启用记录帧。</weconduct-graph>

## 持久断点

在非活动 Debug 状态下，右键节点添加断点，配置写入节点 `debugger.breakpoint` 并随项目保存。可设置：

- `pause_timing`：`before`、`after` 或 `both`
- `hit_count`：达到指定命中次数后暂停
- `once`：本会话只暂停一次
- `expression`：条件表达式

条件错误会产生 `debug.breakpoint_condition_error` 诊断。

## 临时断点与记录帧

会话暂停时，可以右键节点更新临时断点或记录帧。它们通过活动会话的 debugger 覆盖生效，不把图标记为已修改，也不会自动写回项目。

记录帧命中产生 `record_frame.hit`，但 `pause_requested = false`，因此只记录快照，不暂停流程。断点命中产生 `breakpoint.hit`，随后产生 `debug.paused`。

每个命中事件包含稳定的 `frame_identity`、节点、实例路径和迭代信息，用于区分循环和组件中的多次命中。
