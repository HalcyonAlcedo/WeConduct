---
product: weconduct
version: 0.9.1
doc_id: weconduct:legacy:http-group
---

# 旧 HTTP 节点分组

0.9.1 已将旧的 `http.request` 节点升级为 `network.http_request`，并把 HTTP、GraphQL、SSE、WebSocket、上传、下载、响应断言和批量请求统一放入[网络自动化](../network/index.md)分组。

请不要在新项目中继续按本页的旧资源键配置节点。升级旧项目后，程序会通过图升级机制迁移节点和端口；迁移后请重新校验图并检查网络节点的输入输出连线。

前往[网络自动化节点总览](../network/index.md)查看当前 0.9.1 端口和配置。
