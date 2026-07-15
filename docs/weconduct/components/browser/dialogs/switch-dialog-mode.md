---
product: weconduct
version: 0.8.1
doc_id: component:dialog.switch_dialog_mode
---

# 切换对话框模式

资源键：`dialog.switch_dialog_mode`
英文名：Switch Dialog Mode

## 功能说明

切换浏览器对话框处理模式。

该节点属于“对话框处理”。实现类型为 `core_atomic`，运行展开角色为 `action:switch_dialog_mode`。

## 适用场景

在需要“切换对话框模式”能力的流程中使用。

## 前置条件与权限

不要求额外程序权限；仍需满足图结构、输入类型和项目资源约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `mode` | `string` | 否 | `"auto"` | `default` |

## 输入、输出与副作用

输入：`in`。输出：`out`。副作用：主要更新运行时数据。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/dialog-switch-dialog-mode.json" title="切换对话框模式配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "mode": "auto"
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

节点成功后返回 `status = succeeded`，控制流从声明的控制输出继续；无数据输出时通过会话事件和节点结果确认执行。

## 常见错误

端口不存在或关系层不匹配；输入类型与参数要求不一致。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[对话框处理](index.md)聚合页。
- [监听对话框](watch-dialogs.md) (`dialog.watch_dialogs`)。
- [处理对话框](handle-dialogs.md) (`dialog.handle_dialogs`)。
- [设置对话框代理配置](set-agent-config.md) (`dialog.set_agent_config`)。
