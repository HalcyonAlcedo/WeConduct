---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:execution-history
---

# 执行历史

执行历史用于回看已结束的标准运行和 Debug 会话摘要。每条记录以 `session_id` 识别；0.8.1 保存的是会话级摘要，不是完整节点事件、诊断或变量快照归档。

## 查看记录

打开 **任务执行** 面板，在 **执行历史** 区块选择一次会话。摘要包含：

- `session_id`、`status` 和 `graph_model_id`
- `started_at` 和 `completed_at`
- `completed_node_count` 和 `failed_node_count`

**输出 → 历史** 显示的是编译历史，不是运行与 Debug 会话历史。节点事件、诊断详情和 Debug 快照应在对应活动会话或 Debug 历史投影中查看，不能从执行历史摘要恢复。

## 状态解释

- `completed` / `succeeded`：正常完成。
- `failed`：执行或准备失败。
- `aborted` / `cancelled`：用户终止或取消。
- `incomplete`：记录存在但未得到完整终态，常见于进程中断。

历史数据是只读证据。要重跑流程，应回到当前项目图并新建会话，不要把历史记录当成可继续执行的活动会话。
