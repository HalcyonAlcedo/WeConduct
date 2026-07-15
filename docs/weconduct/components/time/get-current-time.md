---
product: weconduct
version: 0.8.1
doc_id: component:time.get_current_time
---

# 获取当前时间

资源键：`time.get_current_time`
英文名：Get Current Time

## 功能说明

读取当前系统时间到运行时输出。

该节点属于“时间处理”。实现类型为 `core_atomic`，运行展开角色为 `action:get_current_time`。

## 适用场景

在流程中生成当前时间文本，用于日志、文件名或业务字段。

## 前置条件与权限

不要求额外程序权限；仍需满足图结构、输入类型和项目资源约束。

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

输入：`in`。输出：`out`、`out:value`。副作用：主要更新运行时数据。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/time/time-get-current-time.json" title="获取当前时间配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "variable_name": "result",
  "format": "iso",
  "timezone": "utc"
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

按配置格式生成时间字符串并写入指定变量。

## 常见错误

端口不存在或关系层不匹配；输入类型与参数要求不一致；时间格式字符串无效或输出变量名为空。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[时间处理](index.md)聚合页。
