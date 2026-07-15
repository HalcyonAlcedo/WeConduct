---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:project-settings
---

# 项目设置

项目设置保存在 `<项目文件名>.data/project-settings.json`，只影响当前项目。通过 **文件 → 项目设置** 修改。

## 项目身份

| 配置 | 默认值 | 作用 |
|---|---|---|
| `name` | `WeConduct Workspace` | 项目显示名 |
0.8.1 的项目设置面板虽然显示 `description`、`version`、`author` 和 `tags`，但加载和保存链路只处理 `name`。不要依赖其他四个输入框保存项目元数据；这是当前版本的已知限制。

`name` 保存后立即生效，不要求重启。

## Debug、资源与打包

- `history_retention_limit = 10`：保留的 Debug 历史上限，影响后续历史写入。
- `external_resources = []`：外部资源声明。
- `embedded_resources = []`：嵌入资源路径。
- `default_output_name`：包管理默认输出名。新项目会按项目文件名或项目名生成初始值，不固定为 `weconduct-project.wcrun`。
- `include_embedded_resources = true`：构建包时包含声明的嵌入资源；0.8.1 面板没有单独开关。

这些设置在下一次保存、历史写入、预检或构建时生效。

## 项目 Python profile

项目 Python profile 从 `runtime_enabled` 到 `package_embed_mode` 共 14 个字段；默认值、作用和生效时机见[项目 Python 运行时](python-runtime.md)。修改 profile 后先保存，再执行健康检查或准备。

完整生命周期见[项目 Python 运行时](python-runtime.md)。

## `.wcrun` 限制

加载 `.wcrun` 后，设置来源为包且大部分字段只读；只允许修改运行默认值。Python profile、资源、打包和保存全部设置不可用。卸载包或打开原项目后恢复编辑。
