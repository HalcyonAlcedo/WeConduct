# 0.6.1 安全设置扩展后端契约

## 范围

本次仅说明后端已落地的首选项 `security_settings` 字段、接口行为、运行时告警与高风险确认链。

不包含视觉设计，不规定页面布局。

## 后端源码位置

- 默认值与归一化：`src/weconduct/application/preferences_store.py:108-131,183-318`
- 首选项更新校验与高风险确认：`src/weconduct/application/preferences_service.py:121-228`
- 快照透传与运行时安全事件：`src/weconduct/application/compilation_workbench_service.py:10835-11174`
- 运行时真实拦截：`src/weconduct/runtime/engine.py:210-295,367-383,549-594,786-878,1012-1103,2293-2303,2949-3434`

## 字段清单

### 执行总开关

- `confirm_high_risk_actions: boolean`
- `show_security_warnings_in_runtime: boolean`
- `log_security_events: boolean`

### 文件访问

- `allow_file_access: boolean`
- `file_access_scope: "restricted" | "custom_roots" | "allow_all"`
- `file_access_allowed_roots: string[]`
- `file_access_blocked_roots: string[]`
- `file_access_allowed_extensions: string[]`
- `file_access_blocked_extensions: string[]`
- `file_access_require_absolute_path: boolean`

说明：

- 路径数组会去空、去重、保留原顺序。
- 扩展名数组会 `trim + lower`，例如 `.TXT` 会归一化为 `.txt`。

### 浏览器能力

- `allow_browser_executor: boolean`
- `allow_browser_screenshots: boolean`
- `allow_cookie_manipulation: boolean`
- `allow_browser_storage_manipulation: boolean`
- `allow_browser_uploads: boolean`
- `allow_browser_downloads: boolean`
- `allow_new_browser_windows: boolean`

### 网络与外部执行

- `allow_external_programs: boolean`
- `allow_local_network_access: boolean`
- `allow_remote_network_access: boolean`
- `allow_python_execution: boolean`

说明：

- `allow_python_execution` 已独立，不再复用 `allow_external_programs`。

### JavaScript 能力

- `allow_js_injection: boolean`
- `allow_js_evaluation: boolean`

## 推荐分组

仅为字段归组建议，UI 可自行组织视觉结构：

1. 执行总开关
2. 文件访问
3. 浏览器能力
4. 网络与外部执行
5. JavaScript 能力

## 接口行为

### 读取

- `GET /api/workbench/preferences`

返回完整 `preferences.security_settings`，新增字段已包含在内。

### 预检

- `POST /api/workbench/preferences/preview`

请求体示例：

```json
{
  "section": "security_settings",
  "values": {
    "allow_python_execution": true
  }
}
```

返回重点：

- `confirmation_required: boolean`
- `high_risk_changes: array`
- `proposed_values`

### 保存

- `POST /api/workbench/preferences`

高风险字段命中时，如果没带：

```json
{
  "confirm_high_risk": true
}
```

后端会返回 `409`，错误码：

- `high_risk_confirmation_required`

## 高风险确认链

以下修改会触发 `preview -> confirm_high_risk`：

- `allow_external_programs: false -> true`
- `allow_browser_executor: false -> true`
- `allow_local_network_access: false -> true`
- `allow_python_execution: false -> true`
- `allow_js_injection: false -> true`
- `allow_js_evaluation: false -> true`
- `allow_remote_network_access: false -> true`
- `file_access_scope: 非 allow_all -> allow_all`
- `file_access_require_absolute_path: true -> false`

## 运行时事件

仅当以下两个值都为 `true` 时，后端会在 runtime 中附加安全事件：

- `log_security_events`
- `show_security_warnings_in_runtime`

当前新增/可见事件种类包括：

- `security.browser_executor.disabled`
- `security.browser_screenshots.disabled`
- `security.cookie_manipulation.disabled`
- `security.browser_storage.disabled`
- `security.browser_uploads.disabled`
- `security.browser_downloads.disabled`
- `security.browser_windows.disabled`
- `security.external_programs.disabled`
- `security.local_network.disabled`
- `security.remote_network.disabled`
- `security.python_execution.disabled`
- `security.js_injection.disabled`
- `security.js_evaluation.disabled`

## 运行时真实限制点

已接入后端真实拦截，不是纯展示字段：

- `allow_browser_screenshots`
  - 拦截 `browser.screenshot`
  - 拦截 `browser.element_screenshot`
  - 错误码：`browser.screenshot_disabled`

- `allow_browser_uploads`
  - 拦截 `browser.set_input_files`
  - 错误码：`browser.upload_disabled`

- `allow_cookie_manipulation`
  - 拦截 `browser.get_cookie / set_cookie / delete_cookie / list_cookies`
  - 错误码：`browser.cookie_manipulation_disabled`

- `allow_new_browser_windows`
  - 拦截 `browser.open_tab`
  - 错误码：`browser.new_window_disabled`

- `allow_browser_downloads`
  - 拦截 `browser.download_file / wait_for_download`
  - 错误码：`browser.download_disabled`

- `allow_js_injection`
  - 拦截 `browser.inject_js`
  - 错误码：`browser.js_injection_disabled`

- `allow_js_evaluation`
  - 拦截 `browser.run_js`
  - 错误码：`browser.js_evaluation_disabled`

- `allow_remote_network_access`
  - 拦截 `http.request` 外网访问
  - 错误码：`http.remote_network_disabled`

- `allow_local_network_access`
  - 拦截 `http.request` 本地/私网访问
  - 错误码：`http.local_network_disabled`

- `allow_python_execution`
  - 拦截 `python.run`
  - 错误码：`python.execution_disabled`

- `file_access_require_absolute_path`
  - 拦截相对路径

- `file_access_blocked_roots`
  - 拦截落入黑名单目录的路径

- `file_access_allowed_extensions`
  - 若配置非空，仅允许这些扩展名

- `file_access_blocked_extensions`
  - 显式禁止这些扩展名

## UI 输入建议

只限定控件类型，不限定样式：

- `boolean` 字段：开关
- `file_access_scope`：单选或下拉
- `*_roots`：目录列表编辑器
- `*_extensions`：字符串列表编辑器

## 已验证命令

以下命令本轮已真实执行通过：

```powershell
pytest tests/application/test_preferences_service.py -q
pytest tests/application/test_workbench_snapshot_service.py -k "browser_screenshot_rejected_when_screenshots_are_disabled or remote_http_request_rejected_when_remote_network_is_disabled or python_run_rejected_when_execution_is_disabled or file_access_scope" -q
pytest tests/api/test_preferences_api.py -q
```

真实结果：

- `tests/application/test_preferences_service.py` -> `10 passed`
- `tests/application/test_workbench_snapshot_service.py ...` -> `5 passed, 309 deselected`
- `tests/api/test_preferences_api.py` -> `2 passed`
