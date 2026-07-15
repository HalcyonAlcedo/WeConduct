---
product: weconduct
version: 0.8.1
doc_id: component:dialog.set_agent_config
---

# 设置对话框代理配置

资源键：`dialog.set_agent_config`　|　英文名：Set Dialog Agent Config
## 功能说明

配置运行时浏览器对话框处理策略。

## 什么时候用

当你需要 设置对话框代理配置 功能时使用。

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
| `default_action` | `string` | 否 | `"accept"` | `default` |
| `prompt_text` | `string` | 是 | `""` | `default` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`。对外影响：更新运行时数据。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/dialog-set-agent-config.json" title="设置对话框代理配置配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "default_action": "accept",
  "prompt_text": "example"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

节点执行成功后，状态为 `succeeded`，控制流继续向下一个节点传递。如果没有数据输出，可以通过运行日志和节点结果确认执行情况。

## 常见问题

缺少必填参数：`prompt_text`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[对话框处理](index.md)聚合页查看更多同类节点。
- [切换对话框模式](switch-dialog-mode.md) (`dialog.switch_dialog_mode`)。
- [监听对话框](watch-dialogs.md) (`dialog.watch_dialogs`)。
- [处理对话框](handle-dialogs.md) (`dialog.handle_dialogs`)。
