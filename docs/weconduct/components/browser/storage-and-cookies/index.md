---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-storage-and-cookies
---

# 存储与 Cookie

覆盖本地存储、会话存储与 Cookie 读写。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [清空本地存储](clear-local-storage.md) | `browser.clear_local_storage` | 清空当前浏览器上下文中的 localStorage。 |
| [删除 Cookie](delete-cookie.md) | `browser.delete_cookie` | 按名称或过滤条件删除当前浏览器上下文中的 Cookie。 |
| [读取 Cookie](get-cookie.md) | `browser.get_cookie` | 从当前浏览器上下文读取 Cookie。 |
| [读取本地存储](get-local-storage.md) | `browser.get_local_storage` | 从当前浏览器上下文读取 localStorage 项并存储结果。 |
| [读取会话存储](get-session-storage.md) | `browser.get_session_storage` | 从当前浏览器上下文读取 sessionStorage 项。 |
| [列出 Cookie](list-cookies.md) | `browser.list_cookies` | 列出当前浏览器上下文中的 Cookie。 |
| [删除本地存储](remove-local-storage.md) | `browser.remove_local_storage` | 从当前浏览器上下文删除 localStorage 项。 |
| [写入 Cookie](set-cookie.md) | `browser.set_cookie` | 向当前浏览器上下文写入 Cookie。 |
| [写入本地存储](set-local-storage.md) | `browser.set_local_storage` | 在当前浏览器上下文写入 localStorage 项。 |
| [写入会话存储](set-session-storage.md) | `browser.set_session_storage` | 在当前浏览器上下文写入 sessionStorage 项。 |

## 常见组合

可从 `清空本地存储 → 删除 Cookie → 读取 Cookie → 读取本地存储` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-storage-and-cookies.json" title="存储与 Cookie节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [清空本地存储](clear-local-storage.md) (`browser.clear_local_storage`)：组件库可见。
- [删除 Cookie](delete-cookie.md) (`browser.delete_cookie`)：组件库可见。
- [读取 Cookie](get-cookie.md) (`browser.get_cookie`)：组件库可见。
- [读取本地存储](get-local-storage.md) (`browser.get_local_storage`)：组件库可见。
- [读取会话存储](get-session-storage.md) (`browser.get_session_storage`)：组件库可见。
- [列出 Cookie](list-cookies.md) (`browser.list_cookies`)：组件库可见。
- [删除本地存储](remove-local-storage.md) (`browser.remove_local_storage`)：组件库可见。
- [写入 Cookie](set-cookie.md) (`browser.set_cookie`)：组件库可见。
- [写入本地存储](set-local-storage.md) (`browser.set_local_storage`)：组件库可见。
- [写入会话存储](set-session-storage.md) (`browser.set_session_storage`)：组件库可见。
