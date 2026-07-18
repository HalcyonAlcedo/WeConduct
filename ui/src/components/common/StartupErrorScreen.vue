<script setup lang="ts">
/** WeConduct — Startup Error Screen
 *  Full-screen, categorized startup-failure UI. Shows severity (严重/故障/异常),
 *  the exact file location of each problem, the error message, and category-
 *  appropriate recovery actions. All text is selectable and one-click copyable.
 */
import { computed, ref } from 'vue'
import { useStartupStore } from '@/stores/startupStore'
import { t } from '@/i18n'
import type { StartupSeverity, StartupSubsystemDiagnostic } from '@/types/domains/api'

const emit = defineEmits<{
  /** Re-run the full startup flow (used by 重试 and after recovery). */
  (e: 'restart'): void
  /** Dismiss and continue into the app (异常 → 强行启动). */
  (e: 'forceStart'): void
}>()

const startup = useStartupStore()

const SEVERITY_META: Record<StartupSeverity, { label: string; tag: string; desc: string }> = {
  critical: {
    label: t('framework.startupError.severity.critical.label', '严重'),
    tag: t('framework.startupError.severity.critical.tag', '无法启动'),
    desc: t('framework.startupError.severity.critical.desc', '程序遇到无法恢复的错误，当前无法启动。请检查后端服务或联系支持。'),
  },
  fault: {
    label: t('framework.startupError.severity.fault.label', '故障'),
    tag: t('framework.startupError.severity.fault.tag', '配置或设置错误导致无法启动'),
    desc: t('framework.startupError.severity.fault.desc', '配置或工作区状态文件损坏/不兼容，导致程序无法启动。可备份并重置为默认配置后强行启动（原文件会保留为备份，但相关配置将丢失）。'),
  },
  anomaly: {
    label: t('framework.startupError.severity.anomaly.label', '异常'),
    tag: t('framework.startupError.severity.anomaly.tag', '不影响使用'),
    desc: t('framework.startupError.severity.anomaly.desc', '软件启动存在问题，但不影响正常使用。可选择强行启动。'),
  },
  ok: { label: t('framework.startupError.severity.ok.label', '正常'), tag: '', desc: '' },
}

const meta = computed(() => SEVERITY_META[startup.severity])
const busy = computed(() => startup.phase === 'recovering' || startup.phase === 'diagnosing')

function severityLabel(s: StartupSeverity): string {
  return SEVERITY_META[s]?.label ?? s
}

// ---- Copy support ----
const copied = ref(false)

function formatSubsystem(s: StartupSubsystemDiagnostic): string {
  const lines: string[] = []
  lines.push(t('framework.startupError.report.subsystemHeader', `[子系统] ${s.label} (${s.subsystem})`, { label: s.label, subsystem: s.subsystem }))
  lines.push(t('framework.startupError.report.status', `  状态: ${s.status}`, { status: s.status }))
  lines.push(t('framework.startupError.report.severity', `  严重度: ${severityLabel(s.severity)} (${s.severity})`, { label: severityLabel(s.severity), severity: s.severity }))
  lines.push(t('framework.startupError.report.location', `  位置: ${s.location}`, { location: s.location }))
  if (s.error_code) lines.push(t('framework.startupError.report.errorCode', `  错误码: ${s.error_code}`, { code: s.error_code }))
  lines.push(t('framework.startupError.report.message', `  信息: ${s.message}`, { message: s.message }))
  const recoverableText = s.recoverable
    ? t('framework.startupError.report.yes', '是')
    : t('framework.startupError.report.no', '否')
  lines.push(t('framework.startupError.report.recoverable', `  可恢复: ${recoverableText}`, { value: recoverableText }))
  return lines.join('\n')
}

function buildReportText(): string {
  const r = startup.report
  const lines: string[] = []
  lines.push(t('framework.startupError.report.title', 'WeConduct 启动错误报告'))
  const generatedAt = r?.generated_at ?? new Date().toISOString()
  lines.push(t('framework.startupError.report.generatedAt', `生成时间: ${generatedAt}`, { time: generatedAt }))
  lines.push(t('framework.startupError.report.severitySummary', `严重度: ${severityLabel(startup.severity)} (${startup.severity}) — ${meta.value.tag}`, { label: severityLabel(startup.severity), severity: startup.severity, tag: meta.value.tag }))
  if (startup.triggerError?.message) lines.push(t('framework.startupError.report.triggerError', `触发错误: ${startup.triggerError.message}`, { message: startup.triggerError.message }))
  if (startup.triggerError?.code) lines.push(t('framework.startupError.report.triggerCode', `触发错误码: ${startup.triggerError.code}`, { code: startup.triggerError.code }))
  if (startup.triggerError?.status != null) lines.push(t('framework.startupError.report.httpStatus', `HTTP 状态: ${startup.triggerError.status}`, { status: startup.triggerError.status }))
  lines.push('')
  for (const s of startup.problemSubsystems) {
    lines.push(formatSubsystem(s))
    lines.push('')
  }
  if (startup.recoverError) lines.push(t('framework.startupError.report.recoverError', `恢复错误: ${startup.recoverError}`, { error: startup.recoverError }))
  return lines.join('\n').trimEnd()
}

async function copyReport() {
  try {
    await navigator.clipboard.writeText(buildReportText())
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch { /* clipboard unavailable */ }
}

async function copyText(text: string) {
  try { await navigator.clipboard.writeText(text) } catch { /* noop */ }
}

// ---- Actions ----
async function onRecoverAndRestart() {
  const ok = await startup.recover()
  if (ok) emit('restart')
}
function onRetry() { emit('restart') }
function onForceStart() { emit('forceStart') }
function onExit() {
  try { window.close() } catch { /* pywebview handles */ }
}
</script>

<template>
  <div class="startup-error" :class="`sev-${startup.severity}`" role="alertdialog" aria-modal="true">
    <div class="se-card">
      <header class="se-header">
        <div class="se-badge">{{ meta.label }}</div>
        <div class="se-title-group">
          <h1 class="se-title">{{ t('framework.startupError.title', '程序启动失败') }}</h1>
          <p class="se-tag">{{ meta.tag }}</p>
        </div>
      </header>

      <p class="se-desc">{{ meta.desc }}</p>

      <section v-if="startup.triggerError" class="se-trigger">
        <span class="se-trigger-label">{{ t('framework.startupError.triggerLabel', '触发错误') }}</span>
        <code class="se-selectable">{{ startup.triggerError.message }}</code>
      </section>

      <section class="se-subsystems">
        <div class="se-section-head">
          <span>{{ t('framework.startupError.problemDetails', `问题详情（${startup.problemSubsystems.length}）`, { n: startup.problemSubsystems.length }) }}</span>
          <button class="se-copy-all" :disabled="busy" @click="copyReport">
            {{ copied ? t('framework.startupError.copied', '✓ 已复制') : t('framework.startupError.copyAll', '📋 复制全部') }}
          </button>
        </div>

        <div
          v-for="s in startup.problemSubsystems"
          :key="s.subsystem"
          class="se-item"
          :class="`sev-${s.severity}`"
        >
          <div class="se-item-head">
            <span class="se-item-sev">{{ severityLabel(s.severity) }}</span>
            <span class="se-item-label">{{ s.label }}</span>
            <span class="se-item-key">{{ s.subsystem }}</span>
            <span v-if="s.recoverable" class="se-item-recoverable">{{ t('framework.startupError.recoverable', '可恢复') }}</span>
          </div>
          <dl class="se-fields">
            <div class="se-field">
              <dt>{{ t('framework.startupError.field.location', '位置') }}</dt>
              <dd>
                <code class="se-selectable">{{ s.location }}</code>
                <button class="se-copy-mini" :title="t('framework.startupError.copyPath', '复制路径')" @click="copyText(s.location)">📋</button>
              </dd>
            </div>
            <div v-if="s.error_code" class="se-field">
              <dt>{{ t('framework.startupError.field.errorCode', '错误码') }}</dt>
              <dd><code class="se-selectable">{{ s.error_code }}</code></dd>
            </div>
            <div class="se-field">
              <dt>{{ t('framework.startupError.field.message', '信息') }}</dt>
              <dd class="se-selectable">{{ s.message }}</dd>
            </div>
          </dl>
        </div>
      </section>

      <p v-if="startup.recoverError" class="se-recover-error se-selectable">
        {{ t('framework.startupError.recoverFailed', `恢复失败：${startup.recoverError}`, { error: startup.recoverError }) }}
      </p>

      <footer class="se-actions">
        <button
          v-if="startup.canRecover"
          class="se-btn se-btn-primary"
          :disabled="busy"
          @click="onRecoverAndRestart"
        >
          {{ startup.phase === 'recovering' ? t('framework.startupError.action.recovering', '恢复中…') : t('framework.startupError.action.recoverAndStart', '用默认配置强行启动') }}
        </button>
        <button
          v-if="startup.canForceStart"
          class="se-btn se-btn-primary"
          :disabled="busy"
          @click="onForceStart"
        >
          {{ t('framework.startupError.action.forceStart', '强行启动') }}
        </button>
        <button class="se-btn" :disabled="busy" @click="onRetry">{{ t('framework.startupError.action.retry', '重试') }}</button>
        <button v-if="startup.severity === 'critical'" class="se-btn" @click="onExit">{{ t('framework.startupError.action.exit', '退出') }}</button>
      </footer>

      <p v-if="startup.canRecover" class="se-hint">
        {{ t('framework.startupError.hintPrefix', '提示：强行启动前会将损坏文件备份为 ') }}<code>.corrupt-*.bak</code>{{ t('framework.startupError.hintSuffix', '，相关配置将重置为默认值。') }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.startup-error {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-xl);
  background: var(--bg-app);
  font-family: var(--font-ui);
  color: var(--text-primary);
  overflow: auto;
}

.se-card {
  width: 100%;
  max-width: 640px;
  background: var(--bg-panel);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-menu);
  padding: var(--space-xl);
  border-top: 4px solid var(--severity-color);
}

/* Severity accent, driven by the root class */
.startup-error.sev-critical { --severity-color: var(--state-fatal); }
.startup-error.sev-fault    { --severity-color: var(--state-error); }
.startup-error.sev-anomaly  { --severity-color: var(--state-degraded); }
.startup-error.sev-ok       { --severity-color: var(--state-success); }

.se-header {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

.se-badge {
  flex-shrink: 0;
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-md);
  background: var(--severity-color);
  color: var(--text-inverse);
  font-weight: 600;
  font-size: var(--text-body);
  letter-spacing: 2px;
}

.se-title { margin: 0; font-size: 18px; font-weight: 600; }
.se-tag { margin: 2px 0 0; font-size: var(--text-small); color: var(--severity-color); font-weight: 500; }

.se-desc {
  margin: 0 0 var(--space-lg);
  font-size: var(--text-body);
  line-height: 1.6;
  color: var(--text-secondary);
}

.se-trigger {
  margin-bottom: var(--space-lg);
  padding: var(--space-md);
  background: var(--bg-input);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}
.se-trigger-label {
  display: block;
  font-size: var(--text-caption);
  color: var(--text-secondary);
  margin-bottom: var(--space-xs);
}
.se-trigger code {
  font-family: var(--font-mono);
  font-size: var(--text-code);
  color: var(--text-primary);
  word-break: break-all;
}

.se-selectable { user-select: text; -webkit-user-select: text; cursor: text; }

.se-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-small);
  color: var(--text-secondary);
  margin-bottom: var(--space-sm);
}
.se-copy-all {
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: var(--text-small);
  padding: 2px var(--space-sm);
  cursor: pointer;
}
.se-copy-all:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); }
.se-copy-all:disabled { opacity: 0.5; cursor: default; }

.se-item {
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--severity-color);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  margin-bottom: var(--space-sm);
  background: var(--bg-input);
}
.se-item.sev-fault    { --severity-color: var(--state-error); }
.se-item.sev-anomaly  { --severity-color: var(--state-degraded); }
.se-item.sev-critical { --severity-color: var(--state-fatal); }

.se-item-head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}
.se-item-sev {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-inverse);
  background: var(--severity-color);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}
.se-item-label { font-weight: 600; font-size: var(--text-body); }
.se-item-key { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
.se-item-recoverable {
  margin-left: auto;
  font-size: var(--text-caption);
  color: var(--state-success);
  border: 1px solid var(--state-success);
  border-radius: var(--radius-sm);
  padding: 0 6px;
}

.se-fields { margin: 0; display: grid; gap: var(--space-xs); }
.se-field { display: grid; grid-template-columns: 48px 1fr; gap: var(--space-sm); align-items: baseline; }
.se-field dt { font-size: var(--text-caption); color: var(--text-secondary); }
.se-field dd { margin: 0; font-size: var(--text-body); line-height: 1.5; display: flex; align-items: baseline; gap: var(--space-xs); }
.se-field code {
  font-family: var(--font-mono);
  font-size: var(--text-small);
  word-break: break-all;
  color: var(--text-primary);
}
.se-copy-mini {
  flex-shrink: 0;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: var(--text-small);
  opacity: 0.5;
  padding: 0;
}
.se-copy-mini:hover { opacity: 1; }

.se-recover-error {
  color: var(--state-error);
  font-size: var(--text-body);
  margin: var(--space-sm) 0 0;
}

.se-actions {
  display: flex;
  gap: var(--space-sm);
  margin-top: var(--space-lg);
  flex-wrap: wrap;
}
.se-btn {
  padding: var(--space-sm) var(--space-lg);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-panel-header);
  color: var(--text-primary);
  font-size: var(--text-body);
  cursor: pointer;
  transition: background 0.15s var(--ease-out);
}
.se-btn:hover:not(:disabled) { background: var(--bg-hover); }
.se-btn:disabled { opacity: 0.5; cursor: default; }
.se-btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--text-inverse);
  font-weight: 500;
}
.se-btn-primary:hover:not(:disabled) { background: var(--accent-hover); }

.se-hint {
  margin: var(--space-md) 0 0;
  font-size: var(--text-caption);
  color: var(--text-secondary);
  line-height: 1.5;
}
.se-hint code { font-family: var(--font-mono); }
</style>
