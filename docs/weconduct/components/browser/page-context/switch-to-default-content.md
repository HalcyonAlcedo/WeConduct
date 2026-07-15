---
product: weconduct
version: 0.8.1
doc_id: component:browser.switch_to_default_content
---

# 切换到默认内容

资源键：`browser.switch_to_default_content`  
英文名：Switch To Default Content

## 功能说明

将浏览器上下文切回顶层页面。

该节点属于“页面上下文”。实现类型为 `core_atomic`，运行展开角色为 `action:switch_to_default_content`。

## 适用场景

完成 iframe 内操作后，返回父级 frame 或顶层页面上下文。

## 前置条件与权限

启用浏览器执行器，并确保存在可用页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |

## 配置参数

该节点没有额外参数；行为由输入、运行上下文或固定语义决定。

## 输入、输出与副作用

输入：`in`。输出：`out`。副作用：改变后续浏览器节点使用的 frame 上下文。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-switch-to-default-content.json" title="切换到默认内容配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

上下文切换成功，后续选择器从新的 frame 层级解析。

## 常见错误

端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[页面上下文](index.md)聚合页。
- [切换到框架](switch-to-frame.md) (`browser.switch_to_frame`)。
- [切换到父框架](switch-to-parent-frame.md) (`browser.switch_to_parent_frame`)。
- [打开框架页面](open-frame-page.md) (`browser.open_frame_page`)。
- [应用认证会话](apply-auth-session.md) (`session.apply_auth_session`)。
- [设置 User-Agent](set-user-agent.md) (`browser.set_user_agent`)。
