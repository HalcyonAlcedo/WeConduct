---
product: weave
version: 0.5.0
stable: true
doc_id: weave:workflows:use-with-weconduct
---

# 与 WeConduct 配合

## 先讲清边界

Weave 0.5.0 和 WeConduct 0.8.x 之间没有直接同步接口。不要把 Weave 当成 WeConduct 的内嵌检查器，也不要期待自动把页面数据推回 WeConduct。

实际可行的是人工传递：

- 选择器
- 当前 URL
- 请求头 / 响应头
- Cookie
- Local Storage / Session Storage 值

## 为什么这样配合是合理的

WeConduct 的多个浏览器相关节点本来就接受 `selector` 字段；会话类节点还支持 `cookies` 和 `local_storage` 参数。因此，Weave 最适合充当“先定位、再人工抄值”的前置分析工具。

## 推荐流程

1. 在 Weave 启动目标页面会话。
2. 用页面树、搜索、叠加层找到目标元素。
3. 在“节点详情”复制运行时选择器和当前 URL。
4. 如果流程依赖登录态，再去“存储管理”抄录 Cookie 或本地存储。
5. 如果接口行为可疑，再去“网络捕获”查看请求和响应细节。
6. 回到 WeConduct，把这些值手工填进节点参数。

## 典型映射

- Weave 的“运行时选择器” -> WeConduct 中各类 `selector`
- Weave 的 Cookie / Local Storage -> WeConduct `session.apply_auth_session`
- Weave 的网络请求细节 -> WeConduct 里后续接口调试或脚本逻辑的人工依据

## 不要这么用

- 不要把 `.weave\` 目录直接当成 WeConduct 项目文件。
- 不要假设切换 Weave 工作区会同时切换 WeConduct 项目。
- 不要把 Weave 插件状态当成 WeConduct 插件状态。
