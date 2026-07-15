---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-page-context
---

# 页面上下文

覆盖框架上下文、会话应用与页面级环境设置。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [打开框架页面](open-frame-page.md) | `browser.open_frame_page` | 将目标框架源作为主页面打开。 |
| [设置额外请求头](set-extra-headers.md) | `browser.set_extra_headers` | 为后续浏览器请求配置额外 HTTP 请求头。 |
| [设置 User-Agent](set-user-agent.md) | `browser.set_user_agent` | 为后续页面配置浏览器 User-Agent。 |
| [切换到默认内容](switch-to-default-content.md) | `browser.switch_to_default_content` | 将浏览器上下文切回顶层页面。 |
| [切换到框架](switch-to-frame.md) | `browser.switch_to_frame` | 将浏览器上下文切换到目标框架。 |
| [切换到父框架](switch-to-parent-frame.md) | `browser.switch_to_parent_frame` | 将浏览器上下文切回父框架。 |
| [应用认证会话](apply-auth-session.md) | `session.apply_auth_session` | 将认证产物应用到浏览器会话。 |

## 常见组合

可从 `打开框架页面 → 设置额外请求头 → 设置 User-Agent → 切换到默认内容` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-page-context.json" title="页面上下文节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [打开框架页面](open-frame-page.md) (`browser.open_frame_page`)：组件库可见。
- [设置额外请求头](set-extra-headers.md) (`browser.set_extra_headers`)：组件库可见。
- [设置 User-Agent](set-user-agent.md) (`browser.set_user_agent`)：组件库可见。
- [切换到默认内容](switch-to-default-content.md) (`browser.switch_to_default_content`)：组件库可见。
- [切换到框架](switch-to-frame.md) (`browser.switch_to_frame`)：组件库可见。
- [切换到父框架](switch-to-parent-frame.md) (`browser.switch_to_parent_frame`)：组件库可见。
- [应用认证会话](apply-auth-session.md) (`session.apply_auth_session`)：组件库可见。
