---
product: weconduct
version: 0.8.1
doc_id: component:http.request
---

# HTTP 请求

资源键：`http.request`
英文名：HTTP Request

## 功能说明

内置 HTTP 请求能力。

该节点属于“HTTP 请求”。实现类型为 `core_atomic`，运行展开角色为 `action:request`。

## 适用场景

向明确的 HTTP URL 发送请求，配置方法、请求头、正文和超时。

## 前置条件与权限

按目标地址启用本地或远程网络访问。

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

输入：`in`、`in:url`。输出：`out`、`out:body`。副作用：访问本地或远程网络目标，并可能对服务端产生写操作。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/http/http-request.json" title="HTTP 请求配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

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

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

请求完成后返回状态码、响应头和解码后的响应内容。

## 常见错误

缺少必填参数：`url`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足；URL 无效、网络权限不足、连接超时或响应解码失败。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

本地和远程目标分别受网络安全权限约束；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[HTTP 请求](index.md)聚合页。
