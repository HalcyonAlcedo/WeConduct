---
product: weconduct
version: 0.8.1
doc_id: component:browser.wait_for_request
---

# 等待请求

资源键：`browser.wait_for_request`
英文名：Wait For Request

## 功能说明

等待观察到匹配条件的浏览器请求。

该节点属于“网络与下载”。实现类型为 `core_atomic`，运行展开角色为 `action:wait_for_request`。

## 适用场景

查询浏览器会话已记录的网络活动，按 URL 模式和可选条件等待匹配的请求。

## 前置条件与权限

启用浏览器执行器，并确保存在可用页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `url_pattern` | `string` | 是 | `""` | `default` |
| `method` | `string` | 是 | `""` | `default` |
| `timeout` | `integer` | 否 | `10000` | `default` |

## 输入、输出与副作用

输入：`in`。输出：`out`、`out:value`。副作用：可能读取或改变页面、浏览器状态、网络记录或本地文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-wait-for-request.json" title="等待请求配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "url_pattern": "example",
  "method": "GET",
  "timeout": 10000
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

在超时前捕获匹配请求后成功，并把捕获记录写入节点结果。

## 常见错误

缺少必填参数：`url_pattern`、`method`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足；URL 模式、方法或状态码未匹配任何请求。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；浏览器会话记录器必须在目标事件发生前已安装，记录最多保留最近 500 条；`timeout` 以毫秒计；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[网络与下载](index.md)聚合页。
- [等待响应](wait-for-response.md) (`browser.wait_for_response`)。
- [下载文件](download-file.md) (`browser.download_file`)。
- [等待下载](wait-for-download.md) (`browser.wait_for_download`)。
