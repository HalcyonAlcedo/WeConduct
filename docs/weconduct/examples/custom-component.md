---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:custom-component
---

# 自定义组件边界

## 场景

使用组件输入、内部变量处理和组件输出组织可复用子图。

## 前置条件

下载项目包含一个自定义组件资源；从资源管理打开组件图查看输入和输出 schema。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/custom-component.json" title="自定义组件边界">图示加载失败时，可按节点职责和配置步骤重建流程。</weconduct-graph>

## 节点职责

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [组件输入](../components/flow/components/input.md) (`component.input`)：在自定义节点图中声明正式组件输入边界。
- [写入变量](../components/data/variables/set-variable.md) (`data.set_variable`)：写入运行时变量。
- [组件输出](../components/flow/components/output.md) (`component.output`)：在自定义节点图中声明正式组件输出边界。

## 配置步骤

1. 下载并解压项目，打开同名 `.weconduct.json` 主文件。
2. 检查图中节点配置，把占位 URL、选择器、路径或凭据替换为实际值。
3. 按前置条件开启最小必要权限，先保存项目，再执行校验和运行。
4. 需要改动控制结构时，只连接各节点端口表中声明的控制或数据端口。

## 预期结果

组件资源暴露 `text` 输入和 `normalized` 输出，主项目可在资源管理中继续编辑。

## 失败诊断

检查组件 schema、资源索引和父子图变量映射；组件边界节点只能用于自定义组件图。

保留诊断中的节点 ID、资源键、原始错误文本和会话状态，再判断是配置、权限、资源还是运行环境问题。

## 下载项目

- [下载 custom-component.zip](../../downloads/weconduct/0.8.1/custom-component.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/custom-component.json)

下载包锁定 WeConduct 0.8.1。外部站点、凭据和网络响应不随示例分发。
