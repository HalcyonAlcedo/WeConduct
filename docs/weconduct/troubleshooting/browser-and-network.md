---
product: weconduct
version: 0.8.1
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

## 需要提交的证据

- 节点资源键和 `node_config`（移除凭据）
- 当前 URL、frame 层级和选择器
- 权限字段实际值
- 原始错误码、超时值和目标请求摘要
