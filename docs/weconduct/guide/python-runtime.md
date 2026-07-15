---
product: weconduct
version: 0.8.1
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

## 操作按钮

按钮行为：

- **健康检查**：仅在 `runtime_enabled = true` 时可用，返回 `ready`、`missing`、`stale` 或 `broken`。`disabled` 是未启用时的状态摘要，不是按钮返回值。
- **准备**：创建或更新运行时、安装需求并写入 manifest。
- **重建**：清理后重新准备。
- **清理**：删除项目运行时，状态变为 `missing`。
- **导出**：按 `package_embed_mode` 导出 ZIP；`none` 时不可导出。

## `.wcrun`

加载 `.wcrun` 后，Python 设置与操作均不可用。包使用构建时写入的运行要求和可选嵌入运行时；缺失或不兼容会出现在检查与运行就绪摘要中。
