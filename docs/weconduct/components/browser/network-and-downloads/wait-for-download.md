---
product: weconduct
version: 0.8.1
doc_id: component:browser.wait_for_download
---

# 等待下载

资源键：`browser.wait_for_download`  
英文名：Wait For Download

## 功能说明

等待捕获到浏览器下载。

该节点属于“网络与下载”。实现类型为 `core_atomic`，运行展开角色为 `action:wait_for_download`。

## 适用场景

在触发下载的交互之前或对应控制链中等待浏览器下载事件，并保存下载结果。

## 前置条件与权限

启用浏览器下载和文件访问；启用浏览器执行器，并确保存在可用页面目标。

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

输入：`in`。输出：`out`、`out:value`。副作用：等待下载事件并把文件写入允许的下载目录。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-wait-for-download.json" title="等待下载配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "path": "output/example.txt",
  "timeout": 10000,
  "variable_name": "result"
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

捕获下载事件后返回保存路径，并可按 `variable_name` 写入运行时变量。

## 常见错误

缺少必填参数：`variable_name`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足；超时前没有下载事件，或下载目录不满足文件权限。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[网络与下载](index.md)聚合页。
- [等待请求](wait-for-request.md) (`browser.wait_for_request`)。
- [等待响应](wait-for-response.md) (`browser.wait_for_response`)。
- [下载文件](download-file.md) (`browser.download_file`)。
