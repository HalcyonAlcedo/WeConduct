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

按钮行为：

- **健康检查**：返回 `ready/missing/stale/broken/disabled`。
- **准备**：创建或更新运行时、安装需求并写入 manifest。
- **重建**：清理后重新准备。
- **清理**：删除项目运行时，状态变为 `missing`。
- **导出**：按 `package_embed_mode` 导出 ZIP；`none` 时不可导出。

## `.wcrun`

加载 `.wcrun` 后，Python 设置与操作均不可用。包使用构建时写入的运行要求和可选嵌入运行时；缺失或不兼容会出现在检查与运行就绪摘要中。
