---
product: weconduct
version: 0.9.1
doc_id: component:python.run
---

# 运行 Python

资源键：`python.run`　|　英文名：Run Python
## 功能说明

运行受限的 Python 脚本。

## 什么时候用

需要自定义数据处理且内置节点不足时，在项目 Python 运行时中执行代码。

## 需要什么权限

需要开启 Python 执行权限，并准备好项目的 Python 运行时环境。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `code` | `string` | 是 | `""` | `code` |
| `inputs` | `object` | 否 | `{}` | `default` |
| `input_schema` | `object` | 否 | `{}` | `json` |
| `output_schema` | `object` | 否 | `{}` | `json` |
| `metadata` | `object` | 否 | `{}` | `default` |
| `metadata_schema` | `object` | 否 | `{}` | `json` |
| `data_fields` | `array` | 否 | `[]` | `default` |
| `allow_sensitive_values` | `boolean` | 否 | `false` | `checkbox` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`。对外影响：启动项目运行时子进程，并可读取输入变量、返回可序列化结果。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/python/python-run.json" title="运行 Python配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "code": "result = variables",
  "inputs": {},
  "input_schema": {},
  "output_schema": {},
  "metadata": {},
  "metadata_schema": {},
  "data_fields": [],
  "allow_sensitive_values": false
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

子进程正常结束后返回结果和运行时来源信息。

## 常见问题

缺少必填参数：`code`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；项目 Python 运行时未启用、代码为空、导入被阻止或执行超时。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

仅能返回 JSON 可序列化数据，导入和执行时间受安全策略限制；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[Python 执行](index.md)聚合页查看更多同类节点。
