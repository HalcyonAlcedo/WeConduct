---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:execution-history
---

# 执行历史

执行历史用于回看已结束的标准运行和 Debug 会话。每条记录以 `session_id` 识别，并保存状态、时间、节点结果、事件、诊断和可用的变量快照。

## 查看记录

打开 **输出** 面板的历史标签，选择一次会话。先确认：

- 会话类型和终态
- 开始/结束时间
- 最后执行节点
- 首个失败诊断
- 终止或异常原因

## 状态解释

- `completed` / `succeeded`：正常完成。
- `failed`：执行或准备失败。
- `aborted` / `cancelled`：用户终止或取消。
- `incomplete`：记录存在但未得到完整终态，常见于进程中断。

历史数据是只读证据。要重跑流程，应回到当前项目图并新建会话，不要把历史记录当成可继续执行的活动会话。
