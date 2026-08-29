---
product: weconduct
version: 0.9.1
doc_id: weconduct:example:wcrun-package-workflow
---

# `.wcrun` 打包工作流

## 这个示例做什么

准备一个无外部依赖的流程，用于演示保存、预检、构建、检查和加载 `.wcrun`。

## 准备工作

先保存下载项目，再在 `.wcrun` 包管理中执行预检；选择用户有写权限的输出路径。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/wcrun-package-workflow.json" title="`.wcrun` 打包工作流">如果图示加载失败，你可以按照下方节点职责说明和配置步骤手动重建这个流程。</weconduct-graph>

## 图中使用了哪些节点

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [批量写入变量](../components/data/variables/set-variables-batch.md) (`data.set_variables_batch`)：一次写入多个运行时变量。
- [读取变量](../components/data/variables/get-variable.md) (`data.get_variable`)：读取运行时变量。

## 如何运行

1. 下载 ZIP 并解压到你的项目目录，用 WeConduct 打开其中的 `.weconduct.json` 文件。
2. 逐个检查图中每个节点的配置，将示例中的占位 URL、选择器、文件路径或凭据替换为你自己的实际值。
3. 根据上方的准备工作，在项目设置中开启必要的权限，然后保存项目、执行校验，确认无误后即可运行。
4. 如果你调整了节点之间的连线，请确保每条边都连接到了节点端口表中实际声明的控制端口或数据端口。

## 运行后应该看到什么

标准运行完成后可构建 `.wcrun`；加载包时图和项目设置只读。

## 如果出错怎么办

预检只覆盖已保存图诊断和必需外部资源绑定；Python 与安全要求在检查、加载和运行就绪阶段确认。

排查时建议记录节点的 ID、资源键和完整的错误信息，先判断是配置问题、权限问题还是运行环境问题，再对症解决。

## 下载项目

- [下载 wcrun-package-workflow.zip](../../downloads/weconduct/0.9.1/wcrun-package-workflow.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/wcrun-package-workflow.json)

下载包基于 WeConduct 0.9.1 版本。示例中的 URL、选择器和凭据均为占位值，外部站点和网络响应不随示例分发。
