---
product: weconduct
version: 0.9.0
doc_id: component:message.emit
---

# 消息

资源键：`message.emit`　|　英文名：Message
## 功能说明

将配置消息写入运行诊断。

## 什么时候用

在运行或 Debug 流程中发布一条用户消息，用于进度、提示或错误分支说明。

## 需要什么权限

该节点不需要额外的程序权限，但仍需要满足图结构、输入类型和项目资源的基本约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `message` | `string` | 是 | `""` | `text` |
| `severity` | `string` | 否 | `"info"` | `enum` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`。对外影响：向 Runtime/Debug 诊断和消息面板发布事件。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/input/message-emit.json" title="消息配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "message": "example",
  "severity": "info"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

消息出现在当前会话的消息/诊断视图中，随后继续控制流

## 常见问题

缺少必填参数：`message`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；消息为空、严重级别不受支持或当前会话已经终止。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[输入与消息](index.md)聚合页查看更多同类节点。
- [请求输入](input-request.md) (`input.request`)。
