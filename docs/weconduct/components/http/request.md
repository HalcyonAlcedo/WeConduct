---
product: weconduct
version: 0.8.1
doc_id: component:http.request
---

# HTTP 请求

资源键：`http.request`　|　英文名：HTTP Request
## 功能说明

内置 HTTP 请求能力。

## 什么时候用

向明确的 HTTP URL 发送请求，配置方法、请求头、正文和超时。

## 需要什么权限

需要按目标地址开启本地或远程网络访问。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:url` | input | `data` | `in.url` |
| `out` | output | `control` | `out.control` |
| `out:body` | output | `data` | `out.body` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `method` | `string` | 否 | `"GET"` | `default` |
| `url` | `string` | 是 | `""` | `default` |
| `headers` | `object` | 否 | `{}` | `default` |
| `timeout` | `integer` | 否 | `30` | `default` |
| `body` | `any` | 否 | `null` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:url`。输出端口：`out`、`out:body`。对外影响：访问本地或远程网络目标，并可能对服务端产生写操作。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/http/http-request.json" title="HTTP 请求配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "method": "GET",
  "url": "https://example.com",
  "headers": {},
  "timeout": 30,
  "body": null
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

请求完成后返回状态码、响应头和解码后的响应内容。

## 常见问题

缺少必填参数：`url`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；URL 无效、网络权限不足、连接超时或响应解码失败。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

本地和远程目标分别受网络安全权限约束；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[HTTP 请求](index.md)聚合页查看更多同类节点。
