---
product: weconduct
version: 0.9.0
doc_id: weconduct:troubleshooting:browser-and-network
---

# 浏览器与网络节点失败

## 提示选择器为空

常见错误码：

```text
browser.selector_required
```

在节点配置或数据输入中提供非空选择器。动态页面优先使用稳定属性，并先用等待节点确认元素出现。

## 提示 URL 为空或无法访问

常见错误码包括 `browser.url_required` 和 `browser.url_pattern_required`。检查 URL 是否完整，并按目标启用本地或远程网络权限。

## 浏览器节点全部被安全策略阻止

所有 `browser.*` 节点都依赖 `allow_browser_executor`。上传、下载、截图、Cookie、Storage、JavaScript 和新窗口还有独立权限；只开启当前流程需要的字段。

## 等待请求或响应总是超时

请求/响应等待查询浏览器会话已记录的事件。记录器必须在事件发生前已安装，URL 模式、方法和状态码必须与真实请求一致；记录最多保留最近 `500` 条。

## frame 中找不到元素

先用 `browser.switch_to_frame` 进入正确 frame。frame 被导航或分离后，后续节点可能回退顶层页面；重新定位 frame 后再执行选择器操作。

## 网络节点没有继承认证或会话

网络上下文按 `inherit`、`new`、`anonymous`、`fork`、`switch` 和 `reset` 策略管理。`anonymous` 会清除认证、Cookie 和会话材料；`fork` 会建立与父上下文隔离的分支。执行优先级是有效输入端口、节点配置、网络上下文、程序网络默认值。

认证、TLS、代理、`base_url` 和 `response_limits` 都在网络运行时消费。检查 `network.access_denied`、`network.tls_*`、`network.proxy_*` 和 `network.response_too_large` 诊断，同时确认本地/远程网络权限。响应正文较大时使用 `out:body_ref` 和正文读取能力，不要把引用当作 JSON 字符串直接序列化。

0.9.0 的 `network.graphql_request` 只支持 Query/Mutation；GraphQL Subscription 会稳定返回不支持错误。SSE 和 WebSocket 只提供主动连接、接收/发送、ping 和关闭，不自动重连，也不会直接触发新的图分支。Cookie 只传递名称和值，不是完整浏览器 Cookie Jar。

## 需要提交的证据

- 节点资源键和 `node_config`（移除凭据）
- 当前 URL、frame 层级和选择器
- 权限字段实际值
- 原始错误码、超时值和目标请求摘要
