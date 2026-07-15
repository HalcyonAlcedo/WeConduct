---
product: weconduct
version: 0.8.1
doc_id: component:browser.switch_to_parent_frame
---

# 切换到父框架

资源键：`browser.switch_to_parent_frame`　|　英文名：Switch To Parent Frame
## 功能说明

将浏览器上下文切回父框架。

## 什么时候用

完成 iframe 内操作后，返回父级 frame 或顶层页面上下文。

## 需要什么权限

需要开启浏览器执行器，并确保存在可用的页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |

## 配置参数

该节点没有额外参数，其行为完全由输入数据和运行上下文决定。

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`。对外影响：改变后续浏览器节点使用的 frame 上下文。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-switch-to-parent-frame.json" title="切换到父框架配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

上下文切换成功，后续选择器从新的 frame 层级解析。

## 常见问题

端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[页面上下文](index.md)聚合页查看更多同类节点。
- [切换到框架](switch-to-frame.md) (`browser.switch_to_frame`)。
- [切换到默认内容](switch-to-default-content.md) (`browser.switch_to_default_content`)。
- [打开框架页面](open-frame-page.md) (`browser.open_frame_page`)。
- [应用认证会话](apply-auth-session.md) (`session.apply_auth_session`)。
- [设置 User-Agent](set-user-agent.md) (`browser.set_user_agent`)。
