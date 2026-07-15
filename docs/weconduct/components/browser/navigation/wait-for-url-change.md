---
product: weconduct
version: 0.8.1
doc_id: component:browser.wait_for_url_change
---

# 等待 URL 变化

资源键：`browser.wait_for_url_change`
英文名：Wait For URL Change

## 功能说明

等待当前页面 URL 发生变化并可选匹配指定模式。

该节点属于“页面导航”。实现类型为 `core_atomic`，运行展开角色为 `action:wait_for_url_change`。

## 适用场景

在继续操作前等待页面达到该节点声明的条件，避免用固定延时猜测就绪时机。

## 前置条件与权限

启用浏览器执行器，并确保存在可用页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `from_url` | `string` | 是 | `""` | `default` |
| `url_pattern` | `string` | 是 | `""` | `default` |
| `timeout` | `integer` | 否 | `10000` | `default` |

## 输入、输出与副作用

输入：`in`。输出：`out`、`out:value`。副作用：可能读取或改变页面、浏览器状态、网络记录或本地文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-wait-for-url-change.json" title="等待 URL 变化配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "from_url": "https://example.com",
  "url_pattern": "example",
  "timeout": 10000
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

条件在超时前满足时返回 `status = succeeded`，否则产生超时诊断。

## 常见错误

缺少必填参数：`from_url`、`url_pattern`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；`timeout` 以毫秒计；匹配模式和页面上下文必须与目标元素或 URL 一致；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[页面导航](index.md)聚合页。
- [导航](navigate.md) (`browser.navigate`)。
- [后退](go-back.md) (`browser.go_back`)。
- [前进](go-forward.md) (`browser.go_forward`)。
- [刷新](refresh.md) (`browser.refresh`)。
- [无缓存刷新](refresh-no-cache.md) (`browser.refresh_no_cache`)。
