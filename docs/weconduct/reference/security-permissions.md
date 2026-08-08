---
product: weconduct
version: 0.9.0
doc_id: weconduct:reference:security-permissions
---

# 安全权限参考

安全权限属于程序设置，对所有项目和包生效。高风险能力默认关闭，包加载时可根据运行要求提示放行。

## 权限组

- **文件**：`allow_file_access` 配合受限/自定义/全部范围、目录与扩展名规则。
- **外部程序**：`allow_external_programs`。
- **浏览器**：执行器、截图、Cookie、存储、上传、下载和新窗口分别控制。
- **网络**：本地与远程网络分别控制；HTTP、浏览器和依赖下载还会做目标检查。
- **代码**：Python 执行、JavaScript 注入和求值分别控制；Python 还有导入阻止列表和超时。

## 默认值

默认允许浏览器截图、Cookie、浏览器存储、上传和新窗口；默认禁止文件访问、外部程序、浏览器执行器/下载、本地与远程网络、Python、JavaScript 注入/求值。高风险确认、安全警告和安全事件日志默认开启。

## 文件范围

开启文件访问后，默认 `restricted`。允许根来自项目目录、工作区目录、状态目录、用户 `Downloads` 和 `custom_roots`；0.9.0 不会自动把用户 `Documents` 加入允许根。阻止目录和扩展名规则优先。`allow_all` 会跳过允许根限制，但仍不应绕过阻止规则。

## 包权限提示

`.wcrun` 声明运行所需权限。加载结果区分“安全就绪”和阻断项。一键放行会写入程序配置，不只影响当前包；先检查包来源、资源绑定和具体字段。

权限不足时应保留诊断中的 `setting_field`、节点和消息。不要为排除单个错误一次性开启全部权限。

## 外部 API 与桌面 UI 鉴权

外部 API 的配置字段属于程序安全设置：`external_api_enabled`、`external_api_token`、`external_api_port` 和 `external_api_project_allowed_roots`。外部 API Token 是软件配置，不是项目加密参数；首选项允许用户直接查看、修改和清除它。`external_api_port=0` 使用启动时动态端口，大于 0 时使用固定 loopback 端口，端口变更在下次启动生效。

外部调用使用独立的 `Authorization: Bearer ...` Token。桌面 UI 请求使用程序启动时生成的 `X-WeConduct-Token`，该 Token 只存在当前进程内存中。两类 Token 不能互相替代，外部 Bearer Token 不能访问内部 `/api/*`，内部 UI Token 也不能访问 `/api/ext/v1/*`。

默认只绑定 loopback。非 loopback 监听属于高风险部署方式，不是普通首选项能力；不要通过 CORS、Origin 或“换一个端口”把端口隔离当成身份认证。项目目录允许根仍由 `external_api_project_allowed_roots` 限制。

外部 API 当前不提供 Debug 控制、插件管理、跨机器安全保证或公网服务能力。GraphQL Subscription、方案 C 的统一长连接内核和插件系统属于后续版本。
