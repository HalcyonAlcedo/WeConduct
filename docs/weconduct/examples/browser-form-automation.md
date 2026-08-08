---
product: weconduct
version: 0.9.0
doc_id: weconduct:example:browser-form-automation
---

# 浏览器表单自动化

## 这个示例做什么

打开网页，填写文本字段并提交表单。

## 准备工作

启用浏览器执行器和远程网络权限；把示例 URL 与选择器替换为目标站点真实值。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/browser-form-automation.json" title="浏览器表单自动化">如果图示加载失败，你可以按照下方节点职责说明和配置步骤手动重建这个流程。</weconduct-graph>

## 图中使用了哪些节点

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [导航](../components/browser/navigation/navigate.md) (`browser.navigate`)：导航浏览器到目标 URL。
- [填入](../components/browser/interaction/fill.md) (`browser.fill`)：向浏览器输入框填入内容。
- [点击](../components/browser/interaction/click.md) (`browser.click`)：点击浏览器中的目标元素。

## 如何运行

1. 下载 ZIP 并解压到你的项目目录，用 WeConduct 打开其中的 `.weconduct.json` 文件。
2. 逐个检查图中每个节点的配置，将示例中的占位 URL、选择器、文件路径或凭据替换为你自己的实际值。
3. 根据上方的准备工作，在项目设置中开启必要的权限，然后保存项目、执行校验，确认无误后即可运行。
4. 如果你调整了节点之间的连线，请确保每条边都连接到了节点端口表中实际声明的控制端口或数据端口。

## 运行后应该看到什么

浏览器进入目标页面，字段值变为 `WeConduct`，随后触发表单提交。

## 如果出错怎么办

优先检查 `allow_browser_executor`、网络权限、URL 和两个选择器；动态页面可在填写前增加条件等待。

排查时建议记录节点的 ID、资源键和完整的错误信息，先判断是配置问题、权限问题还是运行环境问题，再对症解决。

## 下载项目

- [下载 browser-form-automation.zip](../../downloads/weconduct/0.9.0/browser-form-automation.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/browser-form-automation.json)

下载包基于 WeConduct 0.9.0 版本。示例中的 URL、选择器和凭据均为占位值，外部站点和网络响应不随示例分发。
