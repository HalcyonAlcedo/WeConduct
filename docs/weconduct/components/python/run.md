---
product: weconduct
version: 0.8.1
doc_id: component:python.run
---

# 运行 Python

资源键：`python.run`
英文名：Run Python

## 功能说明

运行受限的 Python 脚本。

该节点属于“Python 执行”。实现类型为 `未声明`，运行展开角色为 `action:python_run`。

## 适用场景

需要自定义数据处理且内置节点不足时，在项目 Python 运行时中执行代码。

## 前置条件与权限

启用 Python 执行，并准备项目 Python 运行时。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `code` | `string` | 是 | `""` | `code` |

## 输入、输出与副作用

输入：`in`。输出：`out`。副作用：启动项目运行时子进程，并可读取输入变量、返回可序列化结果。

## 使用示例

<weconduct-graph src="../../../assets/graphs/components/python/python-run.json" title="运行 Python配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "code": "result = variables"
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

子进程正常结束后返回结果和运行时来源信息。

## 常见错误

缺少必填参数：`code`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足；项目 Python 运行时未启用、代码为空、导入被阻止或执行超时。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

仅能返回 JSON 可序列化数据，导入和执行时间受安全策略限制；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[Python 执行](index.md)聚合页。
