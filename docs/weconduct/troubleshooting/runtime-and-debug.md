---
product: weconduct
version: 0.8.1
doc_id: weconduct:troubleshooting:runtime-and-debug
---

# 标准运行或 Debug 异常

## 运行停在 preparing

检查项目 Python 自动准备、安全权限和 `.wcrun` 运行就绪摘要。准备阶段失败时先看 `runtime.prepare` 诊断，不要只看前端最终提示。

## 提示会话冲突

常见类别：

```text
debug.session_conflict
```

标准运行和 Debug 不能同时占用同一项目执行上下文。先终止活动运行或 Debug，再启动另一种会话。

## 终止后仍显示正在终止

终止请求先进入 `aborting`，活动节点完成取消清理后才进入 `aborted`。长时间不变化时记录 `session_id`、当前节点和终止前最后事件，不要重复创建新会话。

## Debug 继续后没有再次暂停

确认断点仍启用、临时断点已添加到当前会话，并区分 **继续** 与单步命令。继续会运行到下一个暂停条件或结束；单步完成后才按步进语义暂停。

## 快照为空

快照只在断点命中、手动暂停、步进暂停或记录帧命中时产生。检查事件是否出现 `breakpoint.hit`、`debug.paused` 或 `record_frame.hit`；普通节点完成不会自动生成快照。

## 历史数据不是完整事件归档

任务执行历史只保存会话摘要。完整 Debug 事件和变量快照应在 Debug 历史投影中查看；关闭进程前保留需要的会话证据。
