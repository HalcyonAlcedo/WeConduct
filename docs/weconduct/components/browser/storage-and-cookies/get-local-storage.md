---
product: weconduct
version: 0.8.1
doc_id: component:browser.get_local_storage
---

# 读取本地存储

资源键：`browser.get_local_storage`　|　英文名：Get Local Storage
## 功能说明

从当前浏览器上下文读取 localStorage 项并存储结果。

## 什么时候用

读写当前浏览器上下文的 Cookie 或 Web Storage，用于会话恢复和状态准备。

## 需要什么权限

需要开启浏览器存储操作权限；需要开启浏览器执行器，并确保存在可用的页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:key` | input | `data` | `in.key` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `key` | `string` | 是 | `""` | `text` |
| `variable_name` | `string` | 否 | `""` | `text` |
| `default_value` | `any` | 否 | `null` | `json` |

## 输入、输出与副作用

输入端口：`in`、`in:key`。输出端口：`out`、`out:value`。对外影响：读取、修改或清除浏览器持久状态；写操作会影响后续页面请求。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-get-local-storage.json" title="读取本地存储配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "key": "example",
  "variable_name": "result",
  "default_value": null
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

读取节点返回目标值或默认值；写入和删除节点完成对应状态变更。

## 常见问题

缺少必填参数：`key`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；域、路径、secure 属性和当前页面 origin 会限制数据可见范围；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[存储与 Cookie](index.md)聚合页查看更多同类节点。
- [写入本地存储](set-local-storage.md) (`browser.set_local_storage`)。
- [删除本地存储](remove-local-storage.md) (`browser.remove_local_storage`)。
- [清空本地存储](clear-local-storage.md) (`browser.clear_local_storage`)。
- [读取会话存储](get-session-storage.md) (`browser.get_session_storage`)。
- [写入会话存储](set-session-storage.md) (`browser.set_session_storage`)。
