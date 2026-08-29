---
product: weconduct
version: 0.9.1
doc_id: component:browser.wait_for_response
---

# 等待响应

资源键：`browser.wait_for_response`　|　英文名：Wait For Response
## 功能说明

等待观察到匹配条件的浏览器响应。

## 什么时候用

查询浏览器会话已记录的网络活动，按 URL 模式和可选条件等待匹配的响应。

## 需要什么权限

需要开启浏览器执行器，并确保存在可用的页面目标。

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
| `status_code` | `integer` | 否 | `null` | `default` |
| `timeout` | `integer` | 否 | `10000` | `default` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`、`out:value`。对外影响：可能改变页面状态、浏览器上下文、网络记录或本地文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-wait-for-response.json" title="等待响应配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "url_pattern": "example",
  "status_code": null,
  "timeout": 10000
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

在超时前捕获匹配响应后成功，并把捕获记录写入节点结果。

## 常见问题

缺少必填参数：`url_pattern`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；URL 模式、方法或状态码未匹配任何响应。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；浏览器会话记录器必须在目标事件发生前已安装，记录最多保留最近 500 条；`timeout` 以毫秒计；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[网络与下载](index.md)聚合页查看更多同类节点。
- [等待请求](wait-for-request.md) (`browser.wait_for_request`)。
- [下载文件](download-file.md) (`browser.download_file`)。
- [等待下载](wait-for-download.md) (`browser.wait_for_download`)。
