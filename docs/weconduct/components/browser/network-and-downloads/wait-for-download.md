---
product: weconduct
version: 0.9.0
doc_id: component:browser.wait_for_download
---

# 等待下载

资源键：`browser.wait_for_download`　|　英文名：Wait For Download
## 功能说明

等待捕获到浏览器下载。

## 什么时候用

在触发下载的交互之前或对应控制链中等待浏览器下载事件，并保存下载结果。

## 需要什么权限

需要开启浏览器下载和文件访问；需要开启浏览器执行器，并确保存在可用的页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `path` | `string` | 否 | `""` | `path` |
| `timeout` | `integer` | 否 | `10000` | `default` |
| `variable_name` | `string` | 是 | `""` | `default` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`、`out:value`。对外影响：等待下载事件并把文件写入允许的下载目录。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-wait-for-download.json" title="等待下载配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "path": "output/example.txt",
  "timeout": 10000,
  "variable_name": "result"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

捕获下载事件后返回保存路径，并可按 `variable_name` 写入运行时变量。

## 常见问题

缺少必填参数：`variable_name`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；超时前没有下载事件，或下载目录不满足文件权限。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[网络与下载](index.md)聚合页查看更多同类节点。
- [等待请求](wait-for-request.md) (`browser.wait_for_request`)。
- [等待响应](wait-for-response.md) (`browser.wait_for_response`)。
- [下载文件](download-file.md) (`browser.download_file`)。
