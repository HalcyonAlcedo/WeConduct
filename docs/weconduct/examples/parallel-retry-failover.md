---
product: weconduct
version: 0.9.1
doc_id: weconduct:example:parallel-retry-failover
---

# 并行、重试与故障切换

## 这个示例做什么

并行执行两个变量写入，汇合后进入重试和故障切换结构。

## 准备工作

不需要外部权限；该示例用于讲解控制结构，实际业务需把 attempt/primary/fallback 分支替换为可判定动作。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/parallel-retry-failover.json" title="并行、重试与故障切换">如果图示加载失败，你可以按照下方节点职责说明和配置步骤手动重建这个流程。</weconduct-graph>

## 图中使用了哪些节点

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

## 如何运行

1. 下载 ZIP 并解压到你的项目目录，用 WeConduct 打开其中的 `.weconduct.json` 文件。
2. 逐个检查图中每个节点的配置，将示例中的占位 URL、选择器、文件路径或凭据替换为你自己的实际值。
3. 根据上方的准备工作，在项目设置中开启必要的权限，然后保存项目、执行校验，确认无误后即可运行。
4. 如果你调整了节点之间的连线，请确保每条边都连接到了节点端口表中实际声明的控制端口或数据端口。

## 运行后应该看到什么

左右分支汇合后进入重试；根据结果从 primary、backup 或 failed 路径写入 `route`。

## 如果出错怎么办

检查 fork/join 的分支 key 是否一致、`max_attempts >= 1`，以及所有结构出口是否已连接。

排查时建议记录节点的 ID、资源键和完整的错误信息，先判断是配置问题、权限问题还是运行环境问题，再对症解决。

## 下载项目

- [下载 parallel-retry-failover.zip](../../downloads/weconduct/0.9.1/parallel-retry-failover.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/parallel-retry-failover.json)

下载包基于 WeConduct 0.9.1 版本。示例中的 URL、选择器和凭据均为占位值，外部站点和网络响应不随示例分发。
