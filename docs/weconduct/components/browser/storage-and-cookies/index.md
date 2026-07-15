---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-storage-and-cookies
---

# 存储与 Cookie

覆盖本地存储、会话存储与 Cookie 读写。

## 节点速览

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

## 典型搭配

这类节点通常会按 `清空本地存储 → 删除 Cookie → 读取 Cookie → 读取本地存储` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-storage-and-cookies.json" title="存储与 Cookie节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [清空本地存储](clear-local-storage.md) (`browser.clear_local_storage`)
- [删除 Cookie](delete-cookie.md) (`browser.delete_cookie`)
- [读取 Cookie](get-cookie.md) (`browser.get_cookie`)
- [读取本地存储](get-local-storage.md) (`browser.get_local_storage`)
- [读取会话存储](get-session-storage.md) (`browser.get_session_storage`)
- [列出 Cookie](list-cookies.md) (`browser.list_cookies`)
- [删除本地存储](remove-local-storage.md) (`browser.remove_local_storage`)
- [写入 Cookie](set-cookie.md) (`browser.set_cookie`)
- [写入本地存储](set-local-storage.md) (`browser.set_local_storage`)
- [写入会话存储](set-session-storage.md) (`browser.set_session_storage`)
