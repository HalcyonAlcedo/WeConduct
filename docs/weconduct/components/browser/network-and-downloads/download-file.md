---
product: weconduct
version: 0.8.1
doc_id: component:browser.download_file
---

# 下载文件

资源键：`browser.download_file`　|　英文名：Download File
## 功能说明

将 URL 指向的文件下载到目标路径。

## 什么时候用

已知文件 URL 且不需要页面点击时，直接发起浏览器上下文下载。

## 需要什么权限

需要开启浏览器下载和文件访问；需要开启浏览器执行器，并确保存在可用的页面目标；需要按目标 URL 开启本地或远程网络访问。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:url` | input | `data` | `in.url` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `url` | `string` | 是 | `""` | `default` |
| `path` | `string` | 是 | `""` | `path` |

## 输入、输出与副作用

输入端口：`in`、`in:url`。输出端口：`out`。对外影响：通过直接网络请求访问目标 URL，并把响应内容写入下载目录。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-download-file.json" title="下载文件配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "url": "https://example.com",
  "path": "output/example.txt"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

下载完成后返回最终文件路径和下载元数据。

## 常见问题

缺少必填参数：`url`、`path`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；URL 不可访问、响应不是可下载内容或文件写入被拒绝。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；该节点不复用当前标签页导航，仍受本地/远程网络和文件允许根约束；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[网络与下载](index.md)聚合页查看更多同类节点。
- [等待请求](wait-for-request.md) (`browser.wait_for_request`)。
- [等待响应](wait-for-response.md) (`browser.wait_for_response`)。
- [等待下载](wait-for-download.md) (`browser.wait_for_download`)。
