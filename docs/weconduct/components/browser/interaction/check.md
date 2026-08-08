---
product: weconduct
version: 0.9.0
doc_id: component:browser.check
---

# 勾选

资源键：`browser.check`　|　英文名：Check
## 功能说明

在浏览器中勾选复选框或单选框。

## 什么时候用

在浏览器自动化流程中执行该动作，需要当前页面或浏览器上下文已经就绪。

## 需要什么权限

需要开启浏览器执行器，并确保存在可用的页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:selector` | input | `data` | `in.selector` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `selector` | `string` | 是 | `""` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:selector`。输出端口：`out`。对外影响：可能改变页面状态、浏览器上下文、网络记录或本地文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-check.json" title="勾选配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "selector": "#example"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

节点执行成功后，状态为 `succeeded`，控制流继续向下一个节点传递。如果没有数据输出，可以通过运行日志和节点结果确认执行情况。

## 常见问题

缺少必填参数：`selector`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[页面交互](index.md)聚合页查看更多同类节点。
- [点击](click.md) (`browser.click`)。
- [填入](fill.md) (`browser.fill`)。
- [取消勾选](uncheck.md) (`browser.uncheck`)。
- [设置上传文件](set-input-files.md) (`browser.set_input_files`)。
- [悬停](hover.md) (`browser.hover`)。
