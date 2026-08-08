---
product: weconduct
version: 0.9.0
doc_id: component:input.request
---

# 请求输入

资源键：`input.request`　|　英文名：Input Request
## 功能说明

暂停执行会话，等待多字段表单提交、超时或取消。

## 什么时候用

暂停整个执行会话，等待 UI、CLI 或外部 API 提交多字段表单。

## 需要什么权限

该节点不需要额外的程序权限，但仍需要满足图结构、输入类型和项目资源的基本约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |
| `timed_out` | output | `control` | `out.timed_out` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `fields` | `array` | 是 | `[]` | `input_request_fields` |
| `timeout_seconds` | `number` | 否 | `0` | `number` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`、`timed_out`。对外影响：暂停会话并创建会话级待输入请求。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/input/input-request.json" title="请求输入配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "fields": [],
  "timeout_seconds": 0
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

提交成功后从 `out` 继续；超时先使用已配置的默认值，否则尝试从 `timed_out` 继续；两者都没有时节点失败

## 常见问题

缺少必填参数：`fields`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；字段定义无效、必填字段缺失、类型校验失败、请求超时或会话被终止。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

敏感字段不提供默认值；提交值只在当前会话内存中存在并在日志、事件和历史中脱敏；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[输入与消息](index.md)聚合页查看更多同类节点。
- [消息](message-emit.md) (`message.emit`)。
