---
product: weconduct
version: 0.8.1
doc_id: component:time.get_current_time
---

# 获取当前时间

资源键：`time.get_current_time`　|　英文名：Get Current Time
## 功能说明

读取当前系统时间到运行时输出。

## 什么时候用

在流程中生成当前时间文本，用于日志、文件名或业务字段。

## 需要什么权限

该节点不需要额外的程序权限，但仍需要满足图结构、输入类型和项目资源的基本约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `variable_name` | `string` | 否 | `""` | `text` |
| `format` | `string` | 否 | `"iso"` | `text` |
| `timezone` | `string` | 否 | `"utc"` | `text` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`、`out:value`。对外影响：更新运行时数据。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/time/time-get-current-time.json" title="获取当前时间配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "variable_name": "result",
  "format": "iso",
  "timezone": "utc"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

按配置格式生成时间字符串并写入指定变量。

## 常见问题

端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；时间格式字符串无效或输出变量名为空。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[时间处理](index.md)聚合页查看更多同类节点。
