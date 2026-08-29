---
product: weconduct
version: 0.9.1
doc_id: component:browser.open_frame_page
---

# 打开框架页面

资源键：`browser.open_frame_page`　|　英文名：Open Frame Page
## 功能说明

将目标框架源作为主页面打开。

## 什么时候用

目标元素位于 iframe 时，按选择器、名称、URL 片段或索引定位框架上下文。

## 需要什么权限

需要开启浏览器执行器，并确保存在可用的页面目标。

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

输入端口：`in`。输出端口：`out`。对外影响：切换当前页面操作所使用的 frame 上下文。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-open-frame-page.json" title="打开框架页面配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "selector": "#example",
  "name": "result",
  "url_contains": "example",
  "index": -1
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

成功定位 frame 后，后续选择器操作在该 frame 上下文执行。

## 常见问题

缺少必填参数：`selector`、`name`、`url_contains`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；多个定位条件互相冲突，或没有找到匹配 frame。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[页面上下文](index.md)聚合页查看更多同类节点。
- [切换到框架](switch-to-frame.md) (`browser.switch_to_frame`)。
- [切换到父框架](switch-to-parent-frame.md) (`browser.switch_to_parent_frame`)。
- [切换到默认内容](switch-to-default-content.md) (`browser.switch_to_default_content`)。
- [设置 User-Agent](set-user-agent.md) (`browser.set_user_agent`)。
- [设置额外请求头](set-extra-headers.md) (`browser.set_extra_headers`)。
