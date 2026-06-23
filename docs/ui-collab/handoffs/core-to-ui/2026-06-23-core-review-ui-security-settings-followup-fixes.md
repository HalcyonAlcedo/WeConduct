# 安全设置 UI 返修点

## 结论

本轮安全设置 UI 已完成大部分接入，但当前仍有 3 个功能问题，需要返修后再做人工确认。

涉及文件：

- `ui/src/components/shells/PreferencesPanel.vue`

## 返修项 1：`file_access_blocked_roots` 没有独立编辑能力

### 问题位置

- `ui/src/components/shells/PreferencesPanel.vue:129-134`
- `ui/src/components/shells/PreferencesPanel.vue:159-163`

### 当前问题

当前 `directory_list` 编辑逻辑只实现了：

- `getAllowedRoots()`
- `setAllowedRoots()`
- `addAllowedRoot()`
- `removeAllowedRoot()`
- `pickAllowedRoot()`

这些函数全部硬编码到：

- `security_settings.file_access_allowed_roots`

但模板中的：

- `file_access_allowed_roots`
- `file_access_blocked_roots`

都会走同一套 `directory_list` UI 分支，因此“禁止访问目录”界面上的增删操作，实际改的是“允许访问目录”。

### 期望修复

需要把目录列表编辑器改成“按字段名工作”，至少支持：

- `file_access_allowed_roots`
- `file_access_blocked_roots`

不要复用固定的 `AllowedRoots` 函数名和固定字段。

建议实现方式：

- `getDirectoryList(fieldKey: string)`
- `setDirectoryList(fieldKey: string, next: string[])`
- `addDirectoryItem(fieldKey: string, path: string)`
- `removeDirectoryItem(fieldKey: string, path: string)`
- `pickDirectoryItem(fieldKey: string, title: string)`

## 返修项 2：扩展名字段保存后无法正确回显

### 问题位置

- `ui/src/components/shells/PreferencesPanel.vue:115-124`
- `ui/src/components/shells/PreferencesPanel.vue:166`

### 当前问题

保存时：

- `file_access_allowed_extensions`
- `file_access_blocked_extensions`

会在 `flattenForSave()` 中被转换为 `string[]` 发给后端。

但回填时，文本框显示逻辑只接受：

- `string`
- `number`

如果后端返回的是数组，当前表达式会显示为空字符串。

这会导致用户看到：

- 实际已保存扩展名
- UI 却显示为空

继续保存时还可能把已有值覆盖掉。

### 期望修复

扩展名字段需要双向一致：

1. 后端返回 `string[]` 时，UI 要转成逗号分隔字符串显示
2. 用户编辑字符串保存时，仍按当前逻辑拆成数组提交

建议至少在初始化/刷新时处理：

- `file_access_allowed_extensions`
- `file_access_blocked_extensions`

例如把：

```ts
[".txt", ".json"]
```

显示成：

```text
.txt, .json
```

## 返修项 3：高风险确认保存后未刷新最新首选项

### 问题位置

- `ui/src/components/shells/PreferencesPanel.vue:110-112`

### 当前问题

普通保存路径 `doSave()` 成功后会：

- `fetchPreferences()`
- 用后端返回值回填当前 section

但高风险确认路径 `confirmHighRiskSave()` 成功后只更新了：

- `saveState`

没有重新获取后端最新数据。

这会导致：

- UI 上看到的值可能不是后端归一化后的最终值
- 某些字段在确认后状态滞后

### 期望修复

`confirmHighRiskSave()` 成功后，应与普通保存路径保持一致：

1. 重新调用 `fetchPreferences()`
2. 回填当前 section
3. 对安全设置中的数组/目录列表字段继续做前端归一化显示

## 本轮验证证据

已运行：

```powershell
npx vitest run src/components/shells/PreferencesPanel.test.ts
npm run build
```

真实结果：

- `1 passed`
- `✓ built`

但这两项验证没有覆盖本文件中的上述 3 个交互问题，因此当前仍需返修。
