---
product: weconduct
version: 0.9.0
doc_id: weconduct:examples:index
---

# 可下载示例

以下每个示例都包含详细的说明页、可交互的节点图和完整的项目 ZIP 下载包。所有流程图均使用 WeConduct 0.9.0 的节点格式。

## 示例列表

- [浏览器表单自动化](browser-form-automation.md)：打开网页，填写文本字段并提交表单。 [下载 ZIP](../../downloads/weconduct/0.9.0/browser-form-automation.zip)
- [网页表格导出 Excel](browser-table-to-excel.md)：打开包含表格的页面，将表头和行数据提取到新的 Excel 工作簿。 [下载 ZIP](../../downloads/weconduct/0.9.0/browser-table-to-excel.zip)
- [浏览器认证会话准备](browser-auth-session.md)：在导航前应用 Cookie 与 Local Storage，再检查登录态页面元素。 [下载 ZIP](../../downloads/weconduct/0.9.0/browser-auth-session.zip)
- [列表整理与统计](data-list-processing.md)：创建列表、追加元素、排序，并统计最终长度。 [下载 ZIP](../../downloads/weconduct/0.9.0/data-list-processing.zip)
- [CSV 读取与文本输出](file-csv-transformation.md)：读取项目内示例 CSV 表格，并把处理说明写入文本文件。 [下载 ZIP](../../downloads/weconduct/0.9.0/file-csv-transformation.zip)
- [条件分支与循环](control-branch-and-loop.md)：初始化计数器，通过条件分支进入循环，并在满足退出条件后读取结果。 [下载 ZIP](../../downloads/weconduct/0.9.0/control-branch-and-loop.zip)
- [并行、重试与故障切换](parallel-retry-failover.md)：并行执行两个变量写入，汇合后进入重试和故障切换结构。 [下载 ZIP](../../downloads/weconduct/0.9.0/parallel-retry-failover.zip)
- [HTTP 与 Python 处理](http-and-python-processing.md)：请求 JSON 数据，再在项目 Python 运行时中进行自定义处理。 [下载 ZIP](../../downloads/weconduct/0.9.0/http-and-python-processing.zip)
- [自定义组件边界](custom-component.md)：使用组件输入、内部变量处理和组件输出组织可复用子图。 [下载 ZIP](../../downloads/weconduct/0.9.0/custom-component.zip)
- [`.wcrun` 打包工作流](wcrun-package-workflow.md)：准备一个无外部依赖的流程，用于演示保存、预检、构建、检查和加载 `.wcrun`。 [下载 ZIP](../../downloads/weconduct/0.9.0/wcrun-package-workflow.zip)

## 使用说明

列表处理和 `.wcrun` 打包示例不依赖外部服务，可以直接运行。
浏览器、HTTP、文件和 Python 示例需要你自行替换占位值，并开启对应的权限。
示例中的 URL、选择器和凭据均为占位值，请不要将真实凭据写入示例项目或提交到版本控制系统。
