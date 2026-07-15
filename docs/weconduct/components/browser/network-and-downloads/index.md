---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-network-and-downloads
---

# 网络与下载

覆盖请求等待、响应等待与下载处理。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [下载文件](download-file.md) | `browser.download_file` | 将 URL 指向的文件下载到目标路径。 |
| [等待下载](wait-for-download.md) | `browser.wait_for_download` | 等待捕获到浏览器下载。 |
| [等待请求](wait-for-request.md) | `browser.wait_for_request` | 等待观察到匹配条件的浏览器请求。 |
| [等待响应](wait-for-response.md) | `browser.wait_for_response` | 等待观察到匹配条件的浏览器响应。 |

## 常见组合

可从 `下载文件 → 等待下载 → 等待请求 → 等待响应` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-network-and-downloads.json" title="网络与下载节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [下载文件](download-file.md) (`browser.download_file`)：组件库可见。
- [等待下载](wait-for-download.md) (`browser.wait_for_download`)：组件库可见。
- [等待请求](wait-for-request.md) (`browser.wait_for_request`)：组件库可见。
- [等待响应](wait-for-response.md) (`browser.wait_for_response`)：组件库可见。
