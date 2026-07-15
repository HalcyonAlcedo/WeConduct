---
product: weconduct
version: 0.8.1
doc_id: component:browser.get_inner_html
---

# 读取内部 HTML

资源键：`browser.get_inner_html`  
英文名：Get Inner HTML

## 功能说明

读取目标元素的 inner HTML。

该节点属于“页面状态与内容”。实现类型为 `core_atomic`，运行展开角色为 `action:get_inner_html`。

## 适用场景

用于浏览器自动化流程中，在页面或浏览器上下文已经就绪后完成该动作。

## 前置条件与权限

启用浏览器执行器，并确保存在可用页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:selector` | input | `data` | `in.selector` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `selector` | `string` | 是 | `""` | `default` |
| `variable_name` | `string` | 是 | `""` | `default` |

## 输入、输出与副作用

输入：`in`、`in:selector`。输出：`out`、`out:value`。副作用：可能读取或改变页面、浏览器状态、网络记录或本地文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-get-inner-html.json" title="读取内部 HTML配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "selector": "#example",
  "variable_name": "result"
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

节点成功后返回 `status = succeeded`，并可从 `out:value` 或节点输出字段取得结果。

## 常见错误

缺少必填参数：`selector`、`variable_name`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[页面状态与内容](index.md)聚合页。
- [截图](screenshot.md) (`browser.screenshot`)。
- [元素截图](element-screenshot.md) (`browser.element_screenshot`)。
- [识别验证码](recognize-captcha.md) (`browser.recognize_captcha`)。
- [元素存在](exists.md) (`browser.exists`)。
- [元素可见](is-visible.md) (`browser.is_visible`)。
