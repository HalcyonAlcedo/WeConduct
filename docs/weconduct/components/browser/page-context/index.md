---
product: weconduct
version: 0.9.0
doc_id: component-group:browser-page-context
---

# 页面上下文

覆盖框架上下文、会话应用与页面级环境设置。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [打开框架页面](open-frame-page.md) | `browser.open_frame_page` | 将目标框架源作为主页面打开。 |
| [设置额外请求头](set-extra-headers.md) | `browser.set_extra_headers` | 为后续浏览器请求配置额外 HTTP 请求头。 |
| [设置 User-Agent](set-user-agent.md) | `browser.set_user_agent` | 为后续页面配置浏览器 User-Agent。 |
| [切换到默认内容](switch-to-default-content.md) | `browser.switch_to_default_content` | 将浏览器上下文切回顶层页面。 |
| [切换到框架](switch-to-frame.md) | `browser.switch_to_frame` | 将浏览器上下文切换到目标框架。 |
| [切换到父框架](switch-to-parent-frame.md) | `browser.switch_to_parent_frame` | 将浏览器上下文切回父框架。 |
| [应用认证会话](apply-auth-session.md) | `session.apply_auth_session` | 将认证产物应用到浏览器会话。 |

## 典型搭配

这类节点通常会按 `打开框架页面 → 设置额外请求头 → 设置 User-Agent → 切换到默认内容` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-page-context.json" title="页面上下文节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [打开框架页面](open-frame-page.md) (`browser.open_frame_page`)
- [设置额外请求头](set-extra-headers.md) (`browser.set_extra_headers`)
- [设置 User-Agent](set-user-agent.md) (`browser.set_user_agent`)
- [切换到默认内容](switch-to-default-content.md) (`browser.switch_to_default_content`)
- [切换到框架](switch-to-frame.md) (`browser.switch_to_frame`)
- [切换到父框架](switch-to-parent-frame.md) (`browser.switch_to_parent_frame`)
- [应用认证会话](apply-auth-session.md) (`session.apply_auth_session`)
