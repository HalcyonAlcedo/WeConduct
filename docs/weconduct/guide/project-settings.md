---
product: weconduct
version: 0.9.1
doc_id: weconduct:guide:project-settings
---

# 项目设置

项目设置保存在 `<项目文件名>.data/project-settings.json`，只影响当前项目。通过 **文件 → 项目设置** 修改。

## 项目名称

| 配置 | 默认值 | 作用 |
|---|---|---|
| `name` | `WeConduct Workspace` | 项目的显示名称 |

项目名称保存后立即生效。面板中显示的其他身份字段（如描述、版本号等）在 0.9.1 中暂不会被保存，将在后续版本中完善。

## Debug 与历史

- `history_retention_limit = 10`：保留的 Debug 历史数量上限，超出后旧记录会被清理。

## 加密初始参数

在 **项目设置 → 加密参数** 中维护项目级敏感初始参数。创建时只保存参数名称、参数集合标识和加密信封；参数值不会以明文写入项目设置。

1. 添加参数名称并输入值，设置项目参数密码。
2. 保存后，修改参数或密码需要重新输入当前密码；删除参数集合需要显式确认。
3. 每次标准运行或 Debug 默认弹出解锁窗口。正确密码只在当前会话内解密，并自动创建敏感引用。
4. 运行结束、取消、失败或 Debug 会话终止后，解密值和敏感引用都会撤销；日志、事件、历史和普通诊断只保留脱敏投影。

加密参数名称必须与 `flow.start.initial_variables` 的明文变量名互斥。UI 保存时会拒绝同名；如果用户直接修改项目配置文件制造同名，运行或 Debug 准备阶段会返回 `sensitive_parameter.initial_variable_name_conflict`，不会继续执行。

敏感参数可通过变量表达式提供给标准能力节点，节点在受控消费点读取实际值，但不会把明文写入运行日志。节点配置仍允许直接填写明文敏感值，这是为特殊场景保留的低安全入口，不推荐使用；优先使用加密参数或[待输入节点](encrypted-parameters-and-input.md)。

## 构建与打包

- `default_output_name`：构建 `.wcrun` 包时的默认输出文件名。新项目会根据项目名称自动生成初始值。

## 项目 Python profile

项目 Python profile 从 `runtime_enabled` 到 `package_embed_mode` 共 14 个字段；默认值、作用和生效时机见[项目 Python 运行时](python-runtime.md)。修改 profile 后先保存，再执行健康检查或准备。

完整生命周期见[项目 Python 运行时](python-runtime.md)。

## `.wcrun` 限制

加载 `.wcrun` 后，设置来源为包且大部分字段只读；只允许修改运行默认值。Python profile、资源、打包和保存全部设置不可用。卸载包或打开原项目后恢复编辑。
