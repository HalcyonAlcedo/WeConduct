---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:custom-component
---

# 自定义组件边界

## 这个示例做什么

使用组件输入、内部变量处理和组件输出组织可复用子图。

## 准备工作

下载项目包含一个自定义组件资源；从资源管理打开组件图查看输入和输出 schema。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/custom-component.json" title="自定义组件边界">如果图示加载失败，你可以按照下方节点职责说明和配置步骤手动重建这个流程。</weconduct-graph>

## 图中使用了哪些节点

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [组件输入](../components/flow/components/input.md) (`component.input`)：在自定义节点图中声明正式组件输入边界。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。
- [组件输出](../components/flow/components/output.md) (`component.output`)：在自定义节点图中声明正式组件输出边界。

## 如何运行

1. 下载 ZIP 并解压到你的项目目录，用 WeConduct 打开其中的 `.weconduct.json` 文件。
2. 逐个检查图中每个节点的配置，将示例中的占位 URL、选择器、文件路径或凭据替换为你自己的实际值。
3. 根据上方的准备工作，在项目设置中开启必要的权限，然后保存项目、执行校验，确认无误后即可运行。
4. 如果你调整了节点之间的连线，请确保每条边都连接到了节点端口表中实际声明的控制端口或数据端口。

## 运行后应该看到什么

组件资源暴露 `text` 输入和 `normalized` 输出，主项目可在资源管理中继续编辑。

## 如果出错怎么办

检查组件 schema、资源索引和父子图变量映射；组件边界节点只能用于自定义组件图。

排查时建议记录节点的 ID、资源键和完整的错误信息，先判断是配置问题、权限问题还是运行环境问题，再对症解决。

## 下载项目

- [下载 custom-component.zip](../../downloads/weconduct/0.8.1/custom-component.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/custom-component.json)

下载包基于 WeConduct 0.8.1 版本。示例中的 URL、选择器和凭据均为占位值，外部站点和网络响应不随示例分发。
