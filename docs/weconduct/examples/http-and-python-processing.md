---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:http-and-python-processing
---

# HTTP 与 Python 处理

## 场景

请求 JSON 数据，再在项目 Python 运行时中进行自定义处理。

## 前置条件

启用远程网络和 Python 执行；在项目设置启用并准备项目 Python 运行时。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/http-and-python-processing.json" title="HTTP 与 Python 处理">图示加载失败时，可按节点职责和配置步骤重建流程。</weconduct-graph>

## 节点职责

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [HTTP 请求](../components/http/request.md) (`http.request`)：内置 HTTP 请求能力。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。
- [运行 Python](../components/python/run.md) (`python.run`)：运行受限的 Python 脚本。

## 配置步骤

1. 下载并解压项目，打开同名 `.weconduct.json` 主文件。
2. 检查图中节点配置，把占位 URL、选择器、路径或凭据替换为实际值。
3. 按前置条件开启最小必要权限，先保存项目，再执行校验和运行。
4. 需要改动控制结构时，只连接各节点端口表中声明的控制或数据端口。

## 预期结果

HTTP 节点返回响应摘要，Python 子进程返回可 JSON 序列化的 `result`。

## 失败诊断

检查 URL、远程网络权限、Python runtime 状态、导入阻止列表和执行超时。

保留诊断中的节点 ID、资源键、原始错误文本和会话状态，再判断是配置、权限、资源还是运行环境问题。

## 下载项目

- [下载 http-and-python-processing.zip](../../downloads/weconduct/0.8.1/http-and-python-processing.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/http-and-python-processing.json)

下载包锁定 WeConduct 0.8.1。外部站点、凭据和网络响应不随示例分发。
