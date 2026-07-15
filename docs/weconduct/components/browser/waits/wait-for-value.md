---
product: weconduct
version: 0.8.1
doc_id: component:browser.wait_for_value
---

# 等待值

资源键：`browser.wait_for_value`
英文名：Wait For Value

## 功能说明

等待输入框或元素值匹配预期值。

该节点属于“等待条件”。实现类型为 `core_atomic`，运行展开角色为 `action:wait_for_value`。

## 适用场景

在继续操作前等待页面达到该节点声明的条件，避免用固定延时猜测就绪时机。

## 前置条件与权限

启用浏览器执行器，并确保存在可用页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:selector` | input | `data` | `in.selector` |
| `in:value` | input | `data` | `in.value` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `selector` | `string` | 是 | `""` | `default` |
| `value` | `string` | 是 | `""` | `default` |
| `match_mode` | `string` | 否 | `"equals"` | `default` |
| `timeout` | `integer` | 否 | `10000` | `default` |

## 输入、输出与副作用

输入：`in`、`in:selector`、`in:value`。输出：`out`、`out:value`。副作用：可能读取或改变页面、浏览器状态、网络记录或本地文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-wait-for-value.json" title="等待值配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "selector": "#example",
  "value": "example",
  "match_mode": "equals",
  "timeout": 10000
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

条件在超时前满足时返回 `status = succeeded`，否则产生超时诊断。

## 常见错误

缺少必填参数：`selector`、`value`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；`timeout` 以毫秒计；匹配模式和页面上下文必须与目标元素或 URL 一致；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[等待条件](index.md)聚合页。
- [等待元素](wait-for-element.md) (`browser.wait_for_element`)。
- [等待导航](wait-for-navigation.md) (`browser.wait_for_navigation`)。
- [等待超时](wait-for-timeout.md) (`browser.wait_for_timeout`)。
- [等待文本](wait-for-text.md) (`browser.wait_for_text`)。
- [等待属性](wait-for-attribute.md) (`browser.wait_for_attribute`)。
