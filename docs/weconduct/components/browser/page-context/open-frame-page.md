---
product: weconduct
version: 0.8.1
doc_id: component:browser.open_frame_page
---

# 打开框架页面

资源键：`browser.open_frame_page`  
英文名：Open Frame Page

## 功能说明

将目标框架源作为主页面打开。

该节点属于“页面上下文”。实现类型为 `core_atomic`，运行展开角色为 `action:open_frame_page`。

## 适用场景

目标元素位于 iframe 时，按选择器、名称、URL 片段或索引定位框架上下文。

## 前置条件与权限

启用浏览器执行器，并确保存在可用页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `selector` | `string` | 是 | `""` | `default` |
| `name` | `string` | 是 | `""` | `default` |
| `url_contains` | `string` | 是 | `""` | `default` |
| `index` | `integer` | 否 | `-1` | `default` |

## 输入、输出与副作用

输入：`in`。输出：`out`。副作用：切换当前页面操作所使用的 frame 上下文。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-open-frame-page.json" title="打开框架页面配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "selector": "#example",
  "name": "result",
  "url_contains": "example",
  "index": -1
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

成功定位 frame 后，后续选择器操作在该 frame 上下文执行。

## 常见错误

缺少必填参数：`selector`、`name`、`url_contains`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足；多个定位条件互相冲突，或没有找到匹配 frame。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[页面上下文](index.md)聚合页。
- [切换到框架](switch-to-frame.md) (`browser.switch_to_frame`)。
- [切换到父框架](switch-to-parent-frame.md) (`browser.switch_to_parent_frame`)。
- [切换到默认内容](switch-to-default-content.md) (`browser.switch_to_default_content`)。
- [应用认证会话](apply-auth-session.md) (`session.apply_auth_session`)。
- [设置 User-Agent](set-user-agent.md) (`browser.set_user_agent`)。
