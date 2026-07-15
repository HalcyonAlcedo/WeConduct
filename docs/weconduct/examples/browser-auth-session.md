---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:browser-auth-session
---

# 浏览器认证会话准备

## 这个示例做什么

在导航前应用 Cookie 与 Local Storage，再检查登录态页面元素。

## 准备工作

启用浏览器执行器、Cookie、浏览器存储和远程网络权限；示例凭据仅为占位。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/browser-auth-session.json" title="浏览器认证会话准备">如果图示加载失败，你可以按照下方节点职责说明和配置步骤手动重建这个流程。</weconduct-graph>

## 图中使用了哪些节点

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [应用认证会话](../components/browser/page-context/apply-auth-session.md) (`session.apply_auth_session`)：将认证产物应用到浏览器会话。
- [导航](../components/browser/navigation/navigate.md) (`browser.navigate`)：导航浏览器到目标 URL。
- [元素存在](../components/browser/state-and-content/exists.md) (`browser.exists`)：检查当前页面上是否存在指定选择器。

## 如何运行

1. 下载 ZIP 并解压到你的项目目录，用 WeConduct 打开其中的 `.weconduct.json` 文件。
2. 逐个检查图中每个节点的配置，将示例中的占位 URL、选择器、文件路径或凭据替换为你自己的实际值。
3. 根据上方的准备工作，在项目设置中开启必要的权限，然后保存项目、执行校验，确认无误后即可运行。
4. 如果你调整了节点之间的连线，请确保每条边都连接到了节点端口表中实际声明的控制端口或数据端口。

## 运行后应该看到什么

认证材料进入浏览器上下文，页面打开后把登录元素是否存在写入 `logged_in`。

## 如果出错怎么办

检查 Cookie 的 domain/path/secure 属性、页面 origin、存储键和认证材料是否过期。

排查时建议记录节点的 ID、资源键和完整的错误信息，先判断是配置问题、权限问题还是运行环境问题，再对症解决。

## 下载项目

- [下载 browser-auth-session.zip](../../downloads/weconduct/0.8.1/browser-auth-session.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/browser-auth-session.json)

下载包基于 WeConduct 0.8.1 版本。示例中的 URL、选择器和凭据均为占位值，外部站点和网络响应不随示例分发。
