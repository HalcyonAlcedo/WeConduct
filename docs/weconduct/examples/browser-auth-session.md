---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:browser-auth-session
---

# 浏览器认证会话准备

## 场景

在导航前应用 Cookie 与 Local Storage，再检查登录态页面元素。

## 前置条件

启用浏览器执行器、Cookie、浏览器存储和远程网络权限；示例凭据仅为占位。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/browser-auth-session.json" title="浏览器认证会话准备">图示加载失败时，可按节点职责和配置步骤重建流程。</weconduct-graph>

## 节点职责

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [应用认证会话](../components/browser/page-context/apply-auth-session.md) (`session.apply_auth_session`)：将认证产物应用到浏览器会话。
- [导航](../components/browser/navigation/navigate.md) (`browser.navigate`)：导航浏览器到目标 URL。
- [元素存在](../components/browser/state-and-content/exists.md) (`browser.exists`)：检查当前页面上是否存在指定选择器。

## 配置步骤

1. 下载并解压项目，打开同名 `.weconduct.json` 主文件。
2. 检查图中节点配置，把占位 URL、选择器、路径或凭据替换为实际值。
3. 按前置条件开启最小必要权限，先保存项目，再执行校验和运行。
4. 需要改动控制结构时，只连接各节点端口表中声明的控制或数据端口。

## 预期结果

认证材料进入浏览器上下文，页面打开后把登录元素是否存在写入 `logged_in`。

## 失败诊断

检查 Cookie 的 domain/path/secure 属性、页面 origin、存储键和认证材料是否过期。

保留诊断中的节点 ID、资源键、原始错误文本和会话状态，再判断是配置、权限、资源还是运行环境问题。

## 下载项目

- [下载 browser-auth-session.zip](../../downloads/weconduct/0.8.1/browser-auth-session.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/browser-auth-session.json)

下载包锁定 WeConduct 0.8.1。外部站点、凭据和网络响应不随示例分发。
