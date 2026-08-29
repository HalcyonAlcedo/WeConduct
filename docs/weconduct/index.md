---
product: weconduct
version: 0.9.1
doc_id: weconduct:index
---

# WeConduct 0.9.1

WeConduct 是一个可视化的自动化流程工具。通过拖拽节点、连接端口，你可以快速构建浏览器操作、数据处理、文件读写等各种自动化工作流程——全程不需要写代码。

## 快速上手

如果你是第一次使用 WeConduct，建议按以下顺序阅读：

1. [安装 WeConduct](getting-started/install.md) — 下载、解压并首次启动
2. [创建第一个项目](getting-started/first-project.md) — 从零搭建一个简单的自动化流程
3. [第一次运行](getting-started/first-run.md) — 执行你的第一个流程，看到运行结果
4. [保存和打开](getting-started/save-and-open.md) — 管理你的项目文件

## 核心概念

了解 WeConduct 的基本工作原理，能帮你更快上手：

- [项目与工作区](concepts/projects-and-workspaces.md) — 理解项目结构和工作环境
- [节点、端口与边](concepts/nodes-ports-and-edges.md) — 构成流程图的三个基本元素
- [控制流与数据流](concepts/control-and-data-flow.md) — 节点之间的两种连接方式
- [变量、类型与表达式](concepts/variables-types-and-expressions.md) — 在流程中传递和处理数据
- [子图与自定义组件](concepts/subgraphs-and-components.md) — 把常用流程打包成可复用的模块

## 使用指南

- [图编辑器](guide/graph-editor.md) — 画布操作、快捷键和编辑技巧
- [组件库](guide/component-library.md) — 浏览和使用内置节点
- [节点配置](guide/node-configuration.md) — 为节点设置参数和行为
- [标准运行](guide/runtime.md) — 执行流程并查看结果
- [调试流程](guide/debug-start.md) — 使用断点和单步执行排查问题
- [项目设置](guide/project-settings.md) — 配置项目的运行环境
- [网络自动化](guide/network-automation.md) — 配置会话级网络上下文和网络节点
- [加密参数与待输入](guide/encrypted-parameters-and-input.md) — 处理敏感参数和运行时输入
- [外部 API](guide/external-api.md) — 通过本地 HTTP API 管理项目和执行

## 内置节点

WeConduct 0.9.1 包含 135 个内置节点，其中 129 个可从组件库直接添加，6 个仅用于兼容或内部迁移。
节点覆盖浏览器自动化、网络自动化、数据处理、文件操作、流程控制、运行时输入和 Python 执行等领域。

[浏览全部节点 →](components/index.md)

## 0.9.1 能力边界

0.9.1 延续可控的网络自动化执行，并新增子图（用户组件）资源的独立导入导出和外部 API 的完整 Debug 控制；网络节点可以继承或隔离会话上下文，显式端口可以覆盖本次请求配置；加密初始参数、待输入表单、运行期敏感值脱敏和 Debug 中的受控查看也已纳入标准流程。

以下能力不属于当前版本：GraphQL Subscription、统一长连接状态机、自动重连、由网络事件直接激活图分支、完整浏览器 Cookie Jar、插件系统和插件动态修改 UI。SSE 与 WebSocket 目前是主动拉取式节点；外部 API 仅提供本机受控操作，不提供插件管理、任意本机文件路径或公网部署保证。

## 可下载示例

每个示例都配有说明页、交互式流程图和完整的项目 ZIP 包，你可以直接下载并运行。

[查看示例 →](examples/index.md)

## 下载

WeConduct 0.9.1 面向 Windows x64，提供便携包和安装包两种分发方式：

[GitHub Releases →](https://github.com/HalcyonAlcedo/WeConduct/releases/tag/0.9.1)
