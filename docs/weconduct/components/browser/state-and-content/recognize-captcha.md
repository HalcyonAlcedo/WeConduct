---
product: weconduct
version: 0.9.1
doc_id: component:browser.recognize_captcha
---

# 识别验证码

资源键：`browser.recognize_captcha`　|　英文名：Recognize Captcha
## 功能说明

使用 captcha_ocr 识别验证码图片。

## 什么时候用

在浏览器自动化流程中执行该动作，需要当前页面或浏览器上下文已经就绪。

## 需要什么权限

需要开启浏览器执行器，并确保存在可用的页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:selector` | input | `data` | `in.selector` |
| `in:image_bytes_base64` | input | `data` | `in.image_bytes_base64` |
| `out` | output | `control` | `out.control` |
| `out:text` | output | `data` | `out.text` |
| `out:confidence` | output | `data` | `out.confidence` |
| `out:character_metadata` | output | `data` | `out.character_metadata` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `selector` | `string` | 是 | `""` | `default` |
| `image_bytes_base64` | `string` | 是 | `""` | `default` |
| `target_variable` | `string` | 是 | `""` | `default` |
| `metadata_variable` | `string` | 是 | `""` | `default` |
| `confidence_variable` | `string` | 是 | `""` | `default` |
| `model_name` | `string` | 是 | `""` | `default` |
| `runtime_root` | `string` | 是 | `""` | `default` |
| `enable_char_meta` | `boolean` | 否 | `true` | `default` |
| `candidate_count` | `integer` | 否 | `3` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:selector`、`in:image_bytes_base64`。输出端口：`out`、`out:text`、`out:confidence`、`out:character_metadata`。对外影响：可能改变页面状态、浏览器上下文、网络记录或本地文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-recognize-captcha.json" title="识别验证码配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "selector": "#example",
  "image_bytes_base64": "example",
  "target_variable": "result",
  "metadata_variable": "result",
  "confidence_variable": "result",
  "model_name": "example",
  "runtime_root": "example",
  "enable_char_meta": true,
  "candidate_count": 3
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

节点执行成功后，状态为 `succeeded`。你可以从 `out:text`、`out:confidence`、`out:character_metadata` 端口或节点输出字段获取结果。

## 常见问题

缺少必填参数：`selector`、`image_bytes_base64`、`target_variable`、`metadata_variable`、`confidence_variable`、`model_name`、`runtime_root`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[页面状态与内容](index.md)聚合页查看更多同类节点。
- [截图](screenshot.md) (`browser.screenshot`)。
- [元素截图](element-screenshot.md) (`browser.element_screenshot`)。
- [元素存在](exists.md) (`browser.exists`)。
- [元素可见](is-visible.md) (`browser.is_visible`)。
- [元素可用](is-enabled.md) (`browser.is_enabled`)。
