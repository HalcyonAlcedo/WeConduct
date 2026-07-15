---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:parallel-retry-failover
---

# 并行、重试与故障切换

## 场景

并行执行两个变量写入，汇合后进入重试和故障切换结构。

## 前置条件

不需要外部权限；该示例用于讲解控制结构，实际业务需把 attempt/primary/fallback 分支替换为可判定动作。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/parallel-retry-failover.json" title="并行、重试与故障切换">图示加载失败时，可按节点职责和配置步骤重建流程。</weconduct-graph>

## 节点职责

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [并行分叉](../components/control/parallel/parallel-fork.md) (`control.parallel_fork`)：将一个控制令牌分发到多个命名控制分支。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。
- [并行汇合](../components/control/parallel/join.md) (`control.join`)：等待一个或多个输入控制分支后再释放下一步。
- [重试](../components/control/reliability/retry.md) (`control.retry`)：重试下游分支直到成功或尝试次数耗尽。
- [故障切换](../components/control/reliability/failover.md) (`control.failover`)：主路径失败时切换到备用分支。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。

## 配置步骤

1. 下载并解压项目，打开同名 `.weconduct.json` 主文件。
2. 检查图中节点配置，把占位 URL、选择器、路径或凭据替换为实际值。
3. 按前置条件开启最小必要权限，先保存项目，再执行校验和运行。
4. 需要改动控制结构时，只连接各节点端口表中声明的控制或数据端口。

## 预期结果

左右分支汇合后进入重试；根据结果从 primary、backup 或 failed 路径写入 `route`。

## 失败诊断

检查 fork/join 的分支 key 是否一致、`max_attempts >= 1`，以及所有结构出口是否已连接。

保留诊断中的节点 ID、资源键、原始错误文本和会话状态，再判断是配置、权限、资源还是运行环境问题。

## 下载项目

- [下载 parallel-retry-failover.zip](../../downloads/weconduct/0.8.1/parallel-retry-failover.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/parallel-retry-failover.json)

下载包锁定 WeConduct 0.8.1。外部站点、凭据和网络响应不随示例分发。
