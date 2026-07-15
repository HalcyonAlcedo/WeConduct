---
product: weconduct
version: 0.8.1
doc_id: component:browser.close_tab
---

# 关闭标签页

资源键：`browser.close_tab`  
英文名：Close Tab

## 功能说明

关闭浏览器标签页。

该节点属于“页面导航”。实现类型为 `core_atomic`，运行展开角色为 `action:close_tab`。

## 适用场景

在多标签页或弹窗流程中创建、定位、激活或关闭页面目标。

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
| `index` | `integer` | 否 | `null` | `default` |
| `label` | `string` | 是 | `""` | `default` |
| `current` | `boolean` | 否 | `false` | `default` |

## 输入、输出与副作用

输入：`in`。输出：`out`。副作用：改变浏览器页面集合或当前活动页面。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-close-tab.json" title="关闭标签页配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "index": null,
  "label": "example",
  "current": false
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

目标标签页被定位并按配置激活、关闭或写入变量。

## 常见错误

缺少必填参数：`label`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足；索引、标签或 URL 模式没有匹配可用页面。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[页面导航](index.md)聚合页。
- [导航](navigate.md) (`browser.navigate`)。
- [后退](go-back.md) (`browser.go_back`)。
- [前进](go-forward.md) (`browser.go_forward`)。
- [刷新](refresh.md) (`browser.refresh`)。
- [无缓存刷新](refresh-no-cache.md) (`browser.refresh_no_cache`)。
