---
product: weconduct
version: 0.9.0
doc_id: weconduct:guide:program-settings
---

# 程序设置

程序设置对所有项目生效，通过 **文件 → 首选项** 修改。0.9.0 使用统一配置注册表提供字段、类型、默认值和选项；注册表没有统一的 `restart_required` 标记，以下“生效”列按真实消费位置说明。

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

## 外部 API 与解锁策略

以下字段位于安全设置中：

| 配置 | 默认值 | 作用 | 生效 |
|---|---|---|---|
| `external_api_enabled` | `false` | 开启本机 `/api/ext/v1` 操作面 | 保存后；监听器按程序启动状态生效 |
| `external_api_token` | `null` | 外部 API 使用的 Bearer Token；属于软件配置，可直接查看、修改和清除 | 保存后；监听器按当前配置更新 |
| `external_api_port` | `0` | `0` 使用动态端口；大于 0 时固定监听本机端口 | 下次启动 |
| `external_api_project_allowed_roots` | `[]` | 限制外部 API 可以打开或创建项目的根目录 | 保存后 |
| `encrypted_parameter_unlock_policy` | `always_prompt` | 每次运行或 Debug 都要求输入项目加密参数密码 | 下次会话 |

外部 API Token 不等同于桌面 UI 使用的进程内 `X-WeConduct-Token`。UI Token 每次程序启动重新生成，只在当前进程会话中使用；不要把它当作外部 API 凭据。外部 API 默认只绑定 loopback 地址，非 loopback 暴露不属于普通桌面配置。

固定端口被占用时程序不会静默切换到动态端口，应释放端口或修改设置。外部 API 的完整操作范围见[外部 API](external-api.md)。

## 网络默认值

这些字段位于网络默认设置中，只有网络节点没有通过有效输入端口或节点配置覆盖时才会使用：

| 配置 | 默认值 | 作用 |
|---|---:|---|
| `base_url` | `null` | 为相对 HTTP、GraphQL、SSE 和 WebSocket 地址提供基地址 |
| `timeout_seconds` | `30` | 网络请求未指定超时时的默认秒数 |
| `response_limits.max_bytes` | `0` | 响应总字节上限；`0` 表示不额外限制 |
| `response_limits.max_in_memory_bytes` | `0` | 允许驻留内存的响应上限；超出时使用会话临时文件或拒绝 |

网络节点的有效输入端口优先级最高，其次是节点配置、网络上下文，最后才是这里的程序默认值。

## Python 与 Debug 默认值

| 配置 | 默认值 | 作用 | 生效 |
|---|---|---|---|
| `python_executable_path` | `null` | Python 节点自定义解释器路径 | 下次运行 |
| `timeout_seconds` | `60` | Python 执行超时 | 下次运行 |
| `capture_stdout_stderr` | `true` | 捕获标准输出/错误 | 下次运行 |
| `variable_apply_mode` | `staged` | Debug 变量默认暂存或立即提交 | 下个 Debug 会话 |
| `blocked_import_modules` | `ctypes, importlib, multiprocessing, os, socket, subprocess` | Python 节点导入阻止列表 | 下次运行 |

项目 Python 默认模板还包括：版本 `>=3.11`、缓存位置 `software_cache`、默认项目缓存模式 `full_venv`、需求来源 `inline`、打包嵌入模式 `wheelhouse_rebuild`。它们只用于新项目或新建 profile，不会覆盖已有项目设置。

`variable_apply_mode=staged` 时，Debug 变量修改先进入当前会话的暂存区，点击应用后才写入执行状态；`immediate` 才会在每次编辑提交后立即写入。无论模式如何，修改都不会回写项目图或初始变量配置。

## 更新

`check_updates_on_startup` 默认 `false`。启用后在下次启动检查更新；手动检查不受此开关限制。
