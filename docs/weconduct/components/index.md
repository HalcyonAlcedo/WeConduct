---
product: weconduct
version: 0.8.1
doc_id: weconduct:components:index
---

# 内置节点参考

WeConduct 0.8.1 包含 126 个内置节点：120 个在组件库可见，6 个仅用于兼容或内部图加载。

可以按中文名、英文名或资源键搜索。聚合页用于比较同类节点和常见组合；详情页提供完整端口、配置、权限、诊断和示例。

## 分类

- [流程与组件边界](flow/components/index.md)：覆盖流程入口与组件输入输出边界。（3 个节点）
- [分支控制](control/branching/index.md)：覆盖条件判断与多路分支。（2 个节点）
- [循环控制](control/loops/index.md)：覆盖遍历与条件循环。（2 个节点）
- [并行控制](control/parallel/index.md)：覆盖并行分叉与汇合。（2 个节点）
- [可靠性控制](control/reliability/index.md)：覆盖重试与故障切换。（2 个节点）
- [页面导航](browser/navigation/index.md)：覆盖页面跳转、刷新与标签切换。（9 个节点）
- [页面交互](browser/interaction/index.md)：覆盖点击、输入、选择、拖放和滚动等交互动作。（13 个节点）
- [等待条件](browser/waits/index.md)：覆盖元素、导航、文本和值等等待条件。（7 个节点）
- [页面上下文](browser/page-context/index.md)：覆盖框架上下文、会话应用与页面级环境设置。（7 个节点）
- [页面状态与内容](browser/state-and-content/index.md)：覆盖截图、识别、存在性检查与页面内容读取。（9 个节点）
- [存储与 Cookie](browser/storage-and-cookies/index.md)：覆盖本地存储、会话存储与 Cookie 读写。（10 个节点）
- [网络与下载](browser/network-and-downloads/index.md)：覆盖请求等待、响应等待与下载处理。（4 个节点）
- [脚本与提取](browser/scripts-and-extraction/index.md)：覆盖脚本执行、网页表格提取与结果导出。（4 个节点）
- [对话框处理](browser/dialogs/index.md)：覆盖对话框监听、处理与代理模式切换。（4 个节点）
- [变量读写](data/variables/index.md)：覆盖变量映射、读写与数值增减。（5 个节点）
- [页面取值](data/page-values/index.md)：覆盖文本、属性、值与元素数量读取。（4 个节点）
- [转换与表达式](data/conversion-and-expressions/index.md)：覆盖数据映射、类型转换、表达式和文本替换。（4 个节点）
- [列表处理](data/lists/index.md)：覆盖列表创建、读写、切片、排序与反转。（12 个节点）
- [文本与 CSV 文件](files/text-and-csv/index.md)：覆盖文本文件和 CSV 读取写入。（5 个节点）
- [Excel 读取](excel/read/index.md)：覆盖 Excel 单元格、行和表读取。（3 个节点）
- [Excel 写入与更新](excel/write-and-update/index.md)：覆盖 Excel 写入、整表输出与批量更新。（6 个节点）
- [HTTP 请求](http/index.md)：覆盖 HTTP 请求发送与结果处理。（1 个节点）
- [Python 执行](python/index.md)：覆盖 Python 代码执行。（1 个节点）
- [时间处理](time/index.md)：覆盖当前时间读取。（1 个节点）
- [兼容与内部节点](internal/compatibility/index.md)：覆盖仅为兼容旧图或内部迁移保留的隐藏节点。（6 个节点）

## 阅读方式

先在聚合页选择节点，再进入详情页核对参数。兼容与内部节点不会出现在普通组件库中，不建议用于新流程。

图示使用方法见[内嵌节点图](../reference/embedded-graphs.md)。
