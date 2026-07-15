---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-network-and-downloads
---

# 网络与下载

覆盖请求等待、响应等待与下载处理。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [下载文件](download-file.md) | `browser.download_file` | 将 URL 指向的文件下载到目标路径。 |
| [等待下载](wait-for-download.md) | `browser.wait_for_download` | 等待捕获到浏览器下载。 |
| [等待请求](wait-for-request.md) | `browser.wait_for_request` | 等待观察到匹配条件的浏览器请求。 |
| [等待响应](wait-for-response.md) | `browser.wait_for_response` | 等待观察到匹配条件的浏览器响应。 |

## 典型搭配

这类节点通常会按 `下载文件 → 等待下载 → 等待请求 → 等待响应` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-network-and-downloads.json" title="网络与下载节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [下载文件](download-file.md) (`browser.download_file`)
- [等待下载](wait-for-download.md) (`browser.wait_for_download`)
- [等待请求](wait-for-request.md) (`browser.wait_for_request`)
- [等待响应](wait-for-response.md) (`browser.wait_for_response`)
