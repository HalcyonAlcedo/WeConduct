---
product: weconduct
version: 0.9.1
doc_id: weconduct:legacy:http-request
---

# 旧 HTTP 请求节点

旧资源键 `http.request` 已在 0.9.1 升级为 `network.http_request`。

## 迁移方式

打开旧项目后执行图校验或编译，程序会按图版本升级机制迁移旧节点。迁移完成后应使用新的资源键和端口：

- 节点：`network.http_request`
- 请求正文输入：`in:body`
- 响应体引用输出：`out:body_ref`
- 请求元数据输出：`out:response`、`out:status_code`、`out:headers`、`out:request_id`

当前节点的完整配置、网络上下文和安全限制见[网络 HTTP 请求](../network/http-request.md)。
