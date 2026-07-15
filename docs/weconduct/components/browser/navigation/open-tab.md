---
product: weconduct
version: 0.8.1
doc_id: component:browser.open_tab
---

# 打开标签页

资源键：`browser.open_tab`　|　英文名：Open Tab
## 功能说明

打开新的浏览器标签页。

## 什么时候用

在多标签页或弹窗流程中创建、定位、激活或关闭页面目标。

## 需要什么权限

需要开启浏览器执行器，并确保存在可用的页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:url` | input | `data` | `in.url` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `url` | `string` | 是 | `""` | `default` |
| `label` | `string` | 是 | `""` | `default` |
| `activate` | `boolean` | 否 | `true` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:url`。输出端口：`out`、`out:value`。对外影响：改变浏览器页面集合或当前活动页面。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-open-tab.json" title="打开标签页配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "url": "https://example.com",
  "label": "example",
  "activate": true
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

目标标签页被定位并按配置激活、关闭或写入变量。

## 常见问题

缺少必填参数：`url`、`label`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；索引、标签或 URL 模式没有匹配可用页面。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[页面导航](index.md)聚合页查看更多同类节点。
- [导航](navigate.md) (`browser.navigate`)。
- [后退](go-back.md) (`browser.go_back`)。
- [前进](go-forward.md) (`browser.go_forward`)。
- [刷新](refresh.md) (`browser.refresh`)。
- [无缓存刷新](refresh-no-cache.md) (`browser.refresh_no_cache`)。
