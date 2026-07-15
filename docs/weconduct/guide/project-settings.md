---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:project-settings
---

# 项目设置

项目设置保存在 `<项目文件名>.data/project-settings.json`，只影响当前项目。通过 **文件 → 项目设置** 修改。

## 项目名称

| 配置 | 默认值 | 作用 |
|---|---|---|
| `name` | `WeConduct Workspace` | 项目的显示名称 |

项目名称保存后立即生效。面板中显示的其他身份字段（如描述、版本号等）在 0.8.1 中暂不会被保存，将在后续版本中完善。

## Debug 与历史

- `history_retention_limit = 10`：保留的 Debug 历史数量上限，超出后旧记录会被清理。

## 构建与打包

- `default_output_name`：构建 `.wcrun` 包时的默认输出文件名。新项目会根据项目名称自动生成初始值。

## 项目 Python profile

项目 Python profile 从 `runtime_enabled` 到 `package_embed_mode` 共 14 个字段；默认值、作用和生效时机见[项目 Python 运行时](python-runtime.md)。修改 profile 后先保存，再执行健康检查或准备。

完整生命周期见[项目 Python 运行时](python-runtime.md)。

## `.wcrun` 限制

加载 `.wcrun` 后，设置来源为包且大部分字段只读；只允许修改运行默认值。Python profile、资源、打包和保存全部设置不可用。卸载包或打开原项目后恢复编辑。
