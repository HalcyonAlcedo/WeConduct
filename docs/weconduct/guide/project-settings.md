---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:project-settings
---

# 项目设置

项目设置保存在项目 `.data/project-settings.json`，只影响当前项目。通过 **文件 → 项目设置** 修改。

## 项目身份

| 配置 | 默认值 | 作用 |
|---|---|---|
| `name` | `WeConduct Workspace` | 项目显示名 |
| `description` | 空 | 项目说明 |
| `version` | `0.1.0` | 项目版本 |
| `author` | 空 | 作者 |
| `tags` | `[]` | 分类标签 |

保存后立即用于项目元数据和打包信息，不要求重启。

## Debug、资源与打包

- `history_retention_limit = 10`：保留的 Debug 历史上限，影响后续历史写入。
- `external_resources = []`：外部资源声明。
- `embedded_resources = []`：嵌入资源路径。
- `default_output_name = weconduct-project.wcrun`：包管理默认输出名。
- `include_embedded_resources = true`：构建包时包含声明的嵌入资源。

这些设置在下一次保存、历史写入、预检或构建时生效。

## 项目 Python profile

有效字段包括 `runtime_enabled`、`python_version_spec`、`interpreter_strategy`、`custom_python_path`、两个缓存模式、三种需求来源及路径、索引策略、`auto_prepare_on_run` 和 `package_embed_mode`。修改 profile 后先保存，再执行健康检查或准备。

完整生命周期见[项目 Python 运行时](python-runtime.md)。

## `.wcrun` 限制

加载 `.wcrun` 后，设置来源为包且大部分字段只读；只允许修改运行默认值。Python profile、资源、打包和保存全部设置不可用。卸载包或打开原项目后恢复编辑。
