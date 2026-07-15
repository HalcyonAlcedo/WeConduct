---
product: weconduct
version: 0.8.1
doc_id: component:browser.download_file
---

# 下载文件

资源键：`browser.download_file`
英文名：Download File

## 功能说明

将 URL 指向的文件下载到目标路径。

该节点属于“网络与下载”。实现类型为 `core_atomic`，运行展开角色为 `action:download_file`。

## 适用场景

已知文件 URL 且不需要页面点击时，直接发起浏览器上下文下载。

## 前置条件与权限

启用浏览器下载和文件访问；启用浏览器执行器，并确保存在可用页面目标；按 URL 启用本地或远程网络访问。

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

输入：`in`、`in:url`。输出：`out`。副作用：通过直接网络请求访问目标 URL，并把响应内容写入下载目录。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-download-file.json" title="下载文件配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "url": "https://example.com",
  "path": "output/example.txt"
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

下载完成后返回最终文件路径和下载元数据。

## 常见错误

缺少必填参数：`url`、`path`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足；URL 不可访问、响应不是可下载内容或文件写入被拒绝。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；该节点不复用当前标签页导航，仍受本地/远程网络和文件允许根约束；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[网络与下载](index.md)聚合页。
- [等待请求](wait-for-request.md) (`browser.wait_for_request`)。
- [等待响应](wait-for-response.md) (`browser.wait_for_response`)。
- [等待下载](wait-for-download.md) (`browser.wait_for_download`)。
