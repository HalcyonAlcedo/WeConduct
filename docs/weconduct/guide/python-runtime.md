---
product: weconduct
version: 0.9.1
doc_id: weconduct:guide:python-runtime
---

# 项目 Python 运行时

项目 Python 运行时为需要 Python 的节点提供可重复环境。先在项目设置中启用 `runtime_enabled`。

## 解释器策略

- `bundled`：使用程序随附或管理的解释器。
- `system`：使用系统可发现的 Python。
- `custom_path`：使用 `custom_python_path` 指定的解释器。

`python_version_spec` 默认 `3.13`。解释器不满足版本或不可启动时，健康状态为 `broken`。

## 依赖来源

- `inline`：直接维护 `requirements_inline` 列表。
- `requirements_txt`：读取 `requirements_file_path`。
- `lock_file`：读取 `lock_file_path`。

自定义索引使用 `index_strategy = custom` 和 `custom_index_url`。依赖文件路径应位于允许的项目资源范围内。

## 缓存与准备

缓存位置可选程序缓存或项目缓存；项目缓存模式为 `full_venv` 或 `wheelhouse_rebuild`。`auto_prepare_on_run = true` 时，运行前自动检查并准备环境。

## Profile 字段

| 字段 | 默认值 | 作用与生效时机 |
|---|---|---|
| `runtime_enabled` | `false` | 启用项目运行时；保存后开放健康检查和准备操作 |
| `python_version_spec` | `3.13` | 约束解释器版本；下次检查或准备时生效 |
| `interpreter_strategy` | `bundled` | 选择 `bundled`、`system` 或 `custom_path` |
| `custom_python_path` | `null` | `custom_path` 策略使用的解释器路径 |
| `cache_location_mode` | `software_cache` | 在程序缓存或项目缓存中保存运行时材料 |
| `project_cache_mode` | `wheelhouse_rebuild` | 项目缓存使用完整环境或 wheelhouse 重建 |
| `requirements_source_mode` | `inline` | 选择内联、`requirements.txt` 或锁文件来源 |
| `requirements_inline` | `[]` | `inline` 模式的依赖列表 |
| `requirements_file_path` | `null` | `requirements_txt` 模式的文件路径 |
| `lock_file_path` | `null` | `lock_file` 模式的文件路径 |
| `index_strategy` | `default` | 使用默认或自定义包索引 |
| `custom_index_url` | `null` | `custom` 索引地址 |
| `auto_prepare_on_run` | `true` | 标准运行或 Debug 前自动准备缺失、过期环境 |
| `package_embed_mode` | `wheelhouse_rebuild` | 打包时选择不嵌入、wheelhouse 或完整环境 |

保存字段本身不立即重建环境；健康检查、准备、重建、运行或打包时消费新配置。

## `python.run` 的 0.9.1 执行边界

`python.run` 仍是项目级 Python 环境中的单节点代码执行能力，不是节点插件或环境插件。节点配置可以声明动态的
`input_schema`、`output_schema`、`metadata_schema` 和 `data_fields`，代码通过执行信封访问这些域：

```python
name = ctx.inputs.get("name")
ctx.outputs.set("greeting", f"hello {name}")
ctx.metadata.set("trace", "request-1")
counter = ctx.data.get("counter")
session = ctx.session.info()
network = ctx.network.current()
ctx.cancel.check()
```

`ctx.data` 只允许读取或写入 `data_fields` 中声明的项目变量；未声明的字段会被拒绝。输出和元数据先保存在本次执行的信封中，只有 Python 子进程成功结束且字段校验通过后才一次性提交，失败或取消不会提交部分输出。

当输入端口或 `data_fields` 中包含会话敏感引用时，默认不允许 Python 代码读取明文。只有在节点明确设置
`allow_sensitive_values = true` 后，敏感值才会通过受控 Broker 在子进程内存中解引用；这不会关闭日志、事件、历史和诊断脱敏，也不会把明文写入项目文件。该开关只适合确有必要的脚本，普通网络认证应优先交给标准能力节点消费。

Python 节点返回值、变量、输出和元数据必须可以转换为 JSON；无法直接转换的对象会按运行时规则转为表示字符串。标准输出和错误输出受项目设置控制，并会在返回前按当前会话中的敏感明文做脱敏。

## 操作按钮

按钮行为：

- **健康检查**：仅在 `runtime_enabled = true` 时可用，返回 `ready`、`missing`、`stale` 或 `broken`。`disabled` 是未启用时的状态摘要，不是按钮返回值。
- **准备**：创建或更新运行时、安装需求并写入 manifest。
- **重建**：清理后重新准备。
- **清理**：删除项目运行时，状态变为 `missing`。
- **导出**：按 `package_embed_mode` 导出 ZIP；`none` 时不可导出。

## `.wcrun`

加载 `.wcrun` 后，Python 设置与操作均不可用。包使用构建时写入的运行要求和可选嵌入运行时；缺失或不兼容会出现在检查与运行就绪摘要中。
