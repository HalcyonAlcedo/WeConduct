---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:browser-form-automation
---

# 浏览器表单自动化

## 场景

打开网页，填写文本字段并提交表单。

## 前置条件

启用浏览器执行器和远程网络权限；把示例 URL 与选择器替换为目标站点真实值。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/browser-form-automation.json" title="浏览器表单自动化">图示加载失败时，可按节点职责和配置步骤重建流程。</weconduct-graph>

## 节点职责

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [导航](../components/browser/navigation/navigate.md) (`browser.navigate`)：导航浏览器到目标 URL。
- [填入](../components/browser/interaction/fill.md) (`browser.fill`)：向浏览器输入框填入内容。
- [点击](../components/browser/interaction/click.md) (`browser.click`)：点击浏览器中的目标元素。

## 配置步骤

1. 下载并解压项目，打开同名 `.weconduct.json` 主文件。
2. 检查图中节点配置，把占位 URL、选择器、路径或凭据替换为实际值。
3. 按前置条件开启最小必要权限，先保存项目，再执行校验和运行。
4. 需要改动控制结构时，只连接各节点端口表中声明的控制或数据端口。

## 预期结果

浏览器进入目标页面，字段值变为 `WeConduct`，随后触发表单提交。

## 失败诊断

优先检查 `allow_browser_executor`、网络权限、URL 和两个选择器；动态页面可在填写前增加条件等待。

保留诊断中的节点 ID、资源键、原始错误文本和会话状态，再判断是配置、权限、资源还是运行环境问题。

## 下载项目

- [下载 browser-form-automation.zip](../../downloads/weconduct/0.8.1/browser-form-automation.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/browser-form-automation.json)

下载包锁定 WeConduct 0.8.1。外部站点、凭据和网络响应不随示例分发。
