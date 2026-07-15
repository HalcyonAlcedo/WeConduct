---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:program-settings
---

# 程序设置

程序设置对所有项目生效，通过 **文件 → 首选项** 修改。0.8.1 使用统一配置注册表提供字段、类型、默认值和选项；注册表没有统一的 `restart_required` 标记，以下“生效”列按真实消费位置说明。

## 界面与工作区

| 配置 | 默认值 | 作用 | 生效 |
|---|---|---|---|
| `default_window_size` | `1440 × 900` | 桌面窗口初始尺寸 | 下次启动 |
| `resource_language` | `zh-CN` | 资源名称语言，可选 `zh-CN/en-US` | 保存并刷新资源后 |
| `default_project_directory` | `null` | 新建项目默认目录 | 下次新建 |
| `recent_project_limit` | `10` | 最近项目保留数量 | 下次刷新列表 |
| `preferences_auto_save` | `true` | 首选项控件变更后自动保存 | 立即 |

## 安全

布尔默认值：

- 默认开启：`confirm_high_risk_actions`、`allow_browser_screenshots`、`allow_cookie_manipulation`、`allow_browser_storage_manipulation`、`allow_browser_uploads`、`allow_new_browser_windows`、`show_security_warnings_in_runtime`、`log_security_events`。
- 默认关闭：`allow_external_programs`、`allow_file_access`、`file_access_require_absolute_path`、`allow_browser_executor`、`allow_browser_downloads`、`allow_local_network_access`、`allow_remote_network_access`、`allow_python_execution`、`allow_js_injection`、`allow_js_evaluation`。

文件范围字段包括 `file_access_scope = restricted`、允许/阻止目录和允许/阻止扩展名列表。安全设置在下一次运行或节点安全检查时生效，不要求重启；已运行中的节点不会被回溯重算。

详细说明见[安全权限](../reference/security-permissions.md)。

## Python 与 Debug 默认值

| 配置 | 默认值 | 作用 | 生效 |
|---|---|---|---|
| `python_executable_path` | `null` | Python 节点自定义解释器路径 | 下次运行 |
| `timeout_seconds` | `60` | Python 执行超时 | 下次运行 |
| `capture_stdout_stderr` | `true` | 捕获标准输出/错误 | 下次运行 |
| `variable_apply_mode` | `staged` | Debug 变量默认暂存或立即提交 | 下个 Debug 会话 |
| `blocked_import_modules` | `ctypes, importlib, multiprocessing, os, socket, subprocess` | Python 节点导入阻止列表 | 下次运行 |

项目 Python 默认模板还包括：版本 `>=3.11`、缓存位置 `software_cache`、默认项目缓存模式 `full_venv`、需求来源 `inline`、打包嵌入模式 `wheelhouse_rebuild`。它们只用于新项目或新建 profile，不会覆盖已有项目设置。

## 更新

`check_updates_on_startup` 默认 `false`。启用后在下次启动检查更新；手动检查不受此开关限制。
