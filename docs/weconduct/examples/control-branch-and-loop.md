---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:control-branch-and-loop
---

# 条件分支与循环

## 场景

初始化计数器，通过条件分支进入循环，并在满足退出条件后读取结果。

## 前置条件

不需要外部权限；编辑控制边时必须使用节点声明的 `true/false/loop/done/repeat` 端口。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/control-branch-and-loop.json" title="条件分支与循环">图示加载失败时，可按节点职责和配置步骤重建流程。</weconduct-graph>

## 节点职责

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。
- [条件分支](../components/control/branching/if.md) (`control.if`)：根据布尔条件分支控制流。
- [变量递增](../components/data/variables/increment-variable.md) (`data.increment_variable`)：递增数值型运行时变量。
- [条件循环](../components/control/loops/while.md) (`control.while`)：当条件保持为真时重复控制分支。
- [读取变量](../components/data/variables/get-variable.md) (`data.get_variable`)：读取运行时变量。

## 配置步骤

1. 下载并解压项目，打开同名 `.weconduct.json` 主文件。
2. 检查图中节点配置，把占位 URL、选择器、路径或凭据替换为实际值。
3. 按前置条件开启最小必要权限，先保存项目，再执行校验和运行。
4. 需要改动控制结构时，只连接各节点端口表中声明的控制或数据端口。

## 预期结果

计数器按循环结构递增，完成后读取 `counter`。

## 失败诊断

若图校验失败，检查循环回边是否接到允许的重复入口，以及表达式是否返回布尔值。

保留诊断中的节点 ID、资源键、原始错误文本和会话状态，再判断是配置、权限、资源还是运行环境问题。

## 下载项目

- [下载 control-branch-and-loop.zip](../../downloads/weconduct/0.8.1/control-branch-and-loop.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/control-branch-and-loop.json)

下载包锁定 WeConduct 0.8.1。外部站点、凭据和网络响应不随示例分发。
