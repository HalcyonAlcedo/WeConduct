---
product: weconduct
version: 0.8.1
doc_id: component:browser.set_local_storage
---

# 写入本地存储

资源键：`browser.set_local_storage`  
英文名：Set Local Storage

## 功能说明

在当前浏览器上下文写入 localStorage 项。

该节点属于“存储与 Cookie”。实现类型为 `core_atomic`，运行展开角色为 `action:set_local_storage`。

## 适用场景

读写当前浏览器上下文的 Cookie 或 Web Storage，用于会话恢复和状态准备。

## 前置条件与权限

启用浏览器存储操作；启用浏览器执行器，并确保存在可用页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:key` | input | `data` | `in.key` |
| `in:value` | input | `data` | `in.value` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `key` | `string` | 是 | `""` | `default` |
| `value` | `any` | 否 | `null` | `default` |

## 输入、输出与副作用

输入：`in`、`in:key`、`in:value`。输出：`out`。副作用：读取、修改或清除浏览器持久状态；写操作会影响后续页面请求。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-set-local-storage.json" title="写入本地存储配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "key": "example",
  "value": null
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

读取节点返回目标值或默认值；写入和删除节点完成对应状态变更。

## 常见错误

缺少必填参数：`key`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；域、路径、secure 属性和当前页面 origin 会限制数据可见范围；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[存储与 Cookie](index.md)聚合页。
- [读取本地存储](get-local-storage.md) (`browser.get_local_storage`)。
- [删除本地存储](remove-local-storage.md) (`browser.remove_local_storage`)。
- [清空本地存储](clear-local-storage.md) (`browser.clear_local_storage`)。
- [读取会话存储](get-session-storage.md) (`browser.get_session_storage`)。
- [写入会话存储](set-session-storage.md) (`browser.set_session_storage`)。
