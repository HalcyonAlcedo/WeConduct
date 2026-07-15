---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:http-and-python-processing
---

# HTTP 与 Python 处理

## 这个示例做什么

请求 JSON 数据，再在项目 Python 运行时中进行自定义处理。

## 准备工作

启用远程网络和 Python 执行；在项目设置启用并准备项目 Python 运行时。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/http-and-python-processing.json" title="HTTP 与 Python 处理">如果图示加载失败，你可以按照下方节点职责说明和配置步骤手动重建这个流程。</weconduct-graph>

## 图中使用了哪些节点

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [HTTP 请求](../components/http/request.md) (`http.request`)：内置 HTTP 请求能力。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。
- [运行 Python](../components/python/run.md) (`python.run`)：运行受限的 Python 脚本。

## 如何运行

1. 下载 ZIP 并解压到你的项目目录，用 WeConduct 打开其中的 `.weconduct.json` 文件。
2. 逐个检查图中每个节点的配置，将示例中的占位 URL、选择器、文件路径或凭据替换为你自己的实际值。
3. 根据上方的准备工作，在项目设置中开启必要的权限，然后保存项目、执行校验，确认无误后即可运行。
4. 如果你调整了节点之间的连线，请确保每条边都连接到了节点端口表中实际声明的控制端口或数据端口。

## 运行后应该看到什么

HTTP 节点返回响应摘要，Python 子进程返回可 JSON 序列化的 `result`。

## 如果出错怎么办

检查 URL、远程网络权限、Python runtime 状态、导入阻止列表和执行超时。

排查时建议记录节点的 ID、资源键和完整的错误信息，先判断是配置问题、权限问题还是运行环境问题，再对症解决。

## 下载项目

- [下载 http-and-python-processing.zip](../../downloads/weconduct/0.8.1/http-and-python-processing.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/http-and-python-processing.json)

下载包基于 WeConduct 0.8.1 版本。示例中的 URL、选择器和凭据均为占位值，外部站点和网络响应不随示例分发。
