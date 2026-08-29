---
product: weconduct
version: 0.9.1
doc_id: weconduct:example:control-branch-and-loop
---

# 条件分支与循环

## 这个示例做什么

初始化计数器，通过条件分支进入循环，并在满足退出条件后读取结果。

## 准备工作

不需要外部权限；编辑控制边时必须使用节点声明的 `true/false/loop/done/repeat` 端口。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/control-branch-and-loop.json" title="条件分支与循环">如果图示加载失败，你可以按照下方节点职责说明和配置步骤手动重建这个流程。</weconduct-graph>

## 图中使用了哪些节点

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。
- [条件分支](../components/control/branching/if.md) (`control.if`)：根据布尔条件分支控制流。
- [变量递增](../components/data/variables/increment-variable.md) (`data.increment_variable`)：递增数值型运行时变量。
- [条件循环](../components/control/loops/while.md) (`control.while`)：当条件保持为真时重复控制分支。
- [读取变量](../components/data/variables/get-variable.md) (`data.get_variable`)：读取运行时变量。

## 如何运行

1. 下载 ZIP 并解压到你的项目目录，用 WeConduct 打开其中的 `.weconduct.json` 文件。
2. 逐个检查图中每个节点的配置，将示例中的占位 URL、选择器、文件路径或凭据替换为你自己的实际值。
3. 根据上方的准备工作，在项目设置中开启必要的权限，然后保存项目、执行校验，确认无误后即可运行。
4. 如果你调整了节点之间的连线，请确保每条边都连接到了节点端口表中实际声明的控制端口或数据端口。

## 运行后应该看到什么

计数器按循环结构递增，完成后读取 `counter`。

## 如果出错怎么办

若图校验失败，检查循环回边是否接到允许的重复入口，以及表达式是否返回布尔值。

排查时建议记录节点的 ID、资源键和完整的错误信息，先判断是配置问题、权限问题还是运行环境问题，再对症解决。

## 下载项目

- [下载 control-branch-and-loop.zip](../../downloads/weconduct/0.9.1/control-branch-and-loop.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/control-branch-and-loop.json)

下载包基于 WeConduct 0.9.1 版本。示例中的 URL、选择器和凭据均为占位值，外部站点和网络响应不随示例分发。
