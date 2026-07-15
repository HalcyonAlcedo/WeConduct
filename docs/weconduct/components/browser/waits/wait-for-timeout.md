---
product: weconduct
version: 0.8.1
doc_id: component:browser.wait_for_timeout
---

# 等待超时

资源键：`browser.wait_for_timeout`
英文名：Wait For Timeout

## 功能说明

按固定时长等待。

该节点属于“等待条件”。实现类型为 `core_atomic`，运行展开角色为 `action:wait_for_timeout`。

## 适用场景

在没有可观测页面条件、只能为外部过程留出固定时间时使用；`timeout` 以毫秒计。

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
| `timeout` | `integer` | 否 | `0` | `default` |

## 输入、输出与副作用

输入：`in`。输出：`out`。副作用：可能读取或改变页面、浏览器状态、网络记录或本地文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-wait-for-timeout.json" title="等待超时配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "timeout": 0
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

等待指定毫秒数后返回 `status = succeeded`，随后继续控制流。

## 常见错误

端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；固定等待不会确认页面真的就绪，优先使用元素、文本、请求或响应等待；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[等待条件](index.md)聚合页。
- [等待元素](wait-for-element.md) (`browser.wait_for_element`)。
- [等待导航](wait-for-navigation.md) (`browser.wait_for_navigation`)。
- [等待文本](wait-for-text.md) (`browser.wait_for_text`)。
- [等待属性](wait-for-attribute.md) (`browser.wait_for_attribute`)。
- [等待值](wait-for-value.md) (`browser.wait_for_value`)。
