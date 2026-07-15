---
product: weconduct
version: 0.8.1
doc_id: weconduct:examples:index
---

# 可下载示例

以下示例同时提供说明页、可交互节点图和目录项目 ZIP。所有图固定使用 `graph-v1` 和 WeConduct 0.8.1 节点契约。

## 示例目录

- [浏览器表单自动化](browser-form-automation.md)：打开网页，填写文本字段并提交表单。 [下载 ZIP](../../downloads/weconduct/0.8.1/browser-form-automation.zip)
- [网页表格导出 Excel](browser-table-to-excel.md)：打开包含表格的页面，将表头和行数据提取到新的 Excel 工作簿。 [下载 ZIP](../../downloads/weconduct/0.8.1/browser-table-to-excel.zip)
- [浏览器认证会话准备](browser-auth-session.md)：在导航前应用 Cookie 与 Local Storage，再检查登录态页面元素。 [下载 ZIP](../../downloads/weconduct/0.8.1/browser-auth-session.zip)
- [列表整理与统计](data-list-processing.md)：创建列表、追加元素、排序，并统计最终长度。 [下载 ZIP](../../downloads/weconduct/0.8.1/data-list-processing.zip)
- [CSV 读取与文本输出](file-csv-transformation.md)：读取项目内示例 CSV 表格，并把处理说明写入文本文件。 [下载 ZIP](../../downloads/weconduct/0.8.1/file-csv-transformation.zip)
- [条件分支与循环](control-branch-and-loop.md)：初始化计数器，通过条件分支进入循环，并在满足退出条件后读取结果。 [下载 ZIP](../../downloads/weconduct/0.8.1/control-branch-and-loop.zip)
- [并行、重试与故障切换](parallel-retry-failover.md)：并行执行两个变量写入，汇合后进入重试和故障切换结构。 [下载 ZIP](../../downloads/weconduct/0.8.1/parallel-retry-failover.zip)
- [HTTP 与 Python 处理](http-and-python-processing.md)：请求 JSON 数据，再在项目 Python 运行时中进行自定义处理。 [下载 ZIP](../../downloads/weconduct/0.8.1/http-and-python-processing.zip)
- [自定义组件边界](custom-component.md)：使用组件输入、内部变量处理和组件输出组织可复用子图。 [下载 ZIP](../../downloads/weconduct/0.8.1/custom-component.zip)
- [`.wcrun` 打包工作流](wcrun-package-workflow.md)：准备一个无外部依赖的流程，用于演示保存、预检、构建、检查和加载 `.wcrun`。 [下载 ZIP](../../downloads/weconduct/0.8.1/wcrun-package-workflow.zip)

## 使用边界

数据列表和 `.wcrun` 准备示例不依赖外部服务；浏览器、HTTP、文件、Python 示例需要对应权限或运行环境。
示例 URL、选择器和凭据均为占位值。不要把测试凭据写入项目或提交到版本库。
