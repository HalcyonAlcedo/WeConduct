---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:runtime
---

# 标准运行

标准运行从当前主图创建后端执行会话。顶部运行按钮与任务执行面板进入同一执行链。

## 生命周期

1. **同步图**：把未保存的当前图作为本次运行输入。
2. **自动准备**：检查图、资源、权限和项目 Python 环境；无需手动点击 Prepare。
3. **编译**：依次完成 parse、bind、validate、normalize、lower 和 emit。
4. **启动**：会话进入准备或运行状态，从唯一 `flow.start` 调度。
5. **进度**：节点状态、事件和变量持续写回会话。
6. **收尾**：正常耗尽队列后进入 `completed`，结果状态为 `succeeded`；错误进入 `failed`，用户终止进入 `aborted` 或取消终态。

UI 提示与会话状态不一致时，以后端会话终态和诊断为准。

## 运行期间

运行按钮会切换为终止。任务执行面板显示会话，**输出**面板显示消息、诊断、摘要和历史。标准运行期间不能同时启动 Debug。

终止流程见[终止运行](runtime-abort.md)，历史见[执行历史](execution-history.md)。
