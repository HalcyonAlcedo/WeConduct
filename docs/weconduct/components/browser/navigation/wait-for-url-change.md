---
product: weconduct
version: 0.8.1
doc_id: component:browser.wait_for_url_change
---

# 等待 URL 变化

资源键：`browser.wait_for_url_change`　|　英文名：Wait For URL Change
## 功能说明

等待当前页面 URL 发生变化并可选匹配指定模式。

## 什么时候用

在继续操作前等待页面达到该节点声明的条件，避免用固定延时猜测就绪时机。

## 需要什么权限

需要开启浏览器执行器，并确保存在可用的页面目标。

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

输入端口：`in`。输出端口：`out`、`out:value`。对外影响：可能改变页面状态、浏览器上下文、网络记录或本地文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-wait-for-url-change.json" title="等待 URL 变化配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "from_url": "https://example.com",
  "url_pattern": "example",
  "timeout": 10000
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

条件在超时前满足时返回 `status = succeeded`，否则产生超时诊断。

## 常见问题

缺少必填参数：`from_url`、`url_pattern`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；`timeout` 以毫秒计；匹配模式和页面上下文必须与目标元素或 URL 一致；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[页面导航](index.md)聚合页查看更多同类节点。
- [导航](navigate.md) (`browser.navigate`)。
- [后退](go-back.md) (`browser.go_back`)。
- [前进](go-forward.md) (`browser.go_forward`)。
- [刷新](refresh.md) (`browser.refresh`)。
- [无缓存刷新](refresh-no-cache.md) (`browser.refresh_no_cache`)。
