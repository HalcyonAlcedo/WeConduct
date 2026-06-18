<script setup lang="ts">
import { computed } from 'vue'
import { useCompilationStore } from '@/stores/compilationStore'
import PlaceholderBanner from '@/components/common/PlaceholderBanner.vue'

const compilation = useCompilationStore()

const hasResult = computed(() => !!compilation.view)
const view = computed(() => compilation.view)
const outcome = computed(() => compilation.outcome)

const stageCards = computed(() => view.value?.stage_cards ?? [])
const stageOverview = computed(() => view.value?.stage_overview)
const diagSummary = computed(() => view.value?.diagnostic_summary)
const graphStats = computed(() => view.value?.graph_stats)
const durationLabel = computed(() => {
  const durationMs = view.value?.duration_ms ?? outcome.value?.compilation_summary.duration_ms ?? null
  if (typeof durationMs !== 'number' || Number.isNaN(durationMs)) {
    return '—'
  }
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(2)}s`
  }
  return `${durationMs}ms`
})

const outcomeLabel = computed(() => {
  const status = view.value?.status
  if (status === 'succeeded') return { text: '编译成功', cls: 'badge-success' }
  if (status === 'failed') return { text: '编译失败', cls: 'badge-error' }
  if (status === 'unsupported') return { text: '不支持', cls: 'badge-warning' }
  return null
})

function stageStatusLabel(status: string): { text: string; cls: string } {
  switch (status) {
    case 'succeeded': return { text: '✓ 成功', cls: 'ss-success' }
    case 'failed': return { text: '✕ 失败', cls: 'ss-error' }
    case 'pending': return { text: '◉ 待定', cls: 'ss-pending' }
    default: return { text: status, cls: '' }
  }
}
</script>

<template>
  <div class="summary-tab">
    <!-- No compilation yet -->
    <PlaceholderBanner
      v-if="!hasResult && compilation.compilePhase === 'idle'"
      type="empty"
      title="编译源代码后在此查看结果"
      description="输入源代码并点击「编译」按钮开始"
    />

    <!-- Compiling -->
    <div v-else-if="compilation.isCompiling" class="loading-block">
      <div v-for="i in 4" :key="i" class="skeleton-row skeleton-pulse"></div>
    </div>

    <!-- Results -->
    <template v-else-if="hasResult && view">
      <!-- Outcome Header -->
      <div class="st-section">
        <div v-if="outcomeLabel" :class="['st-badge', outcomeLabel.cls]">
          {{ outcomeLabel.text }}
        </div>
        <div class="st-meta" v-if="outcome">
          编译 ID: {{ outcome.compilation_summary.compilation_id }}
          <span class="st-meta-div">|</span>
          耗时: {{ durationLabel }}
        </div>
      </div>

      <!-- Stage Breakdown -->
      <div class="st-section">
        <h3 class="st-heading">阶段明细</h3>
        <table class="st-table">
          <thead>
            <tr>
              <th>阶段</th>
              <th>状态</th>
              <th>诊断数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="card in stageCards" :key="card.stage">
              <td class="st-stage-name">{{ card.stage }}</td>
              <td>
                <span :class="['st-stage-status', stageStatusLabel(card.status).cls]">
                  {{ stageStatusLabel(card.status).text }}
                </span>
              </td>
              <td>{{ card.diagnostic_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Overview -->
      <div class="st-section" v-if="stageOverview">
        <h3 class="st-heading">概览</h3>
        <div class="st-overview-grid">
          <div class="st-ov-item">
            <span class="st-ov-label">总阶段数</span>
            <span class="st-ov-value">{{ stageOverview.total_stage_count }}</span>
          </div>
          <div class="st-ov-item">
            <span class="st-ov-label">成功</span>
            <span class="st-ov-value success">{{ stageOverview.succeeded_stage_count }}</span>
          </div>
          <div class="st-ov-item">
            <span class="st-ov-label">失败</span>
            <span class="st-ov-value error">{{ stageOverview.failed_stage_count }}</span>
          </div>
          <div class="st-ov-item" v-if="stageOverview.terminal_stage">
            <span class="st-ov-label">终止阶段</span>
            <span class="st-ov-value">{{ stageOverview.terminal_stage }}</span>
          </div>
        </div>
      </div>

      <!-- Diagnostic Summary -->
      <div class="st-section" v-if="diagSummary">
        <h3 class="st-heading">诊断汇总</h3>
        <div class="st-ds">
          总计 {{ diagSummary.total_count }} 条诊断
          <span v-if="diagSummary.highest_severity">
            · 最高严重度: {{ diagSummary.highest_severity }}
          </span>
        </div>
      </div>

      <!-- Graph Stats -->
      <div class="st-section" v-if="graphStats">
        <h3 class="st-heading">图模型</h3>
        <div class="st-ds" v-if="graphStats.graph_model_id">
          {{ graphStats.graph_model_id }}
          · 节点 {{ graphStats.node_count }}
          · 边 {{ graphStats.edge_count }}
        </div>
        <div class="st-ds" v-else>
          未生成图模型
        </div>
      </div>
    </template>

    <!-- Failure state -->
    <PlaceholderBanner
      v-else-if="compilation.compilePhase === 'failed' && !hasResult"
      type="failure"
      :title="compilation.compileError ?? '编译请求失败'"
      description="请检查源代码后重试"
    />
  </div>
</template>

<style scoped>
.summary-tab {
  padding: var(--space-lg);
}

.loading-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-lg);
}

.skeleton-row {
  height: 16px;
  background: var(--bg-panel-header);
  border-radius: var(--radius-sm);
}

.st-section {
  margin-bottom: var(--space-lg);
}

.st-heading {
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-sm);
  padding-bottom: var(--space-xs);
  border-bottom: 1px solid var(--border-subtle);
}

.st-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  font-size: var(--text-small);
  font-weight: 600;
}
.badge-success { background: rgba(107,154,102,0.12); color: var(--state-success); }
.badge-error   { background: rgba(208,112,96,0.12); color: var(--state-error); }
.badge-warning { background: rgba(200,148,74,0.12); color: var(--state-degraded); }

.st-meta {
  font-size: var(--text-small);
  color: var(--text-disabled);
  margin-top: var(--space-xs);
}
.st-meta-div {
  margin: 0 var(--space-sm);
  color: var(--border-default);
}

.st-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-body);
}
.st-table th {
  text-align: left;
  padding: 4px 8px;
  color: var(--text-disabled);
  font-weight: 600;
  font-size: var(--text-small);
  border-bottom: 1px solid var(--border-subtle);
}
.st-table td {
  padding: 4px 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.st-stage-name {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-small);
}

.st-stage-status {
  font-size: var(--text-small);
}
.ss-success { color: var(--state-success); }
.ss-error   { color: var(--state-error); }
.ss-pending { color: var(--text-disabled); }

.st-overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-sm);
}

.st-ov-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.st-ov-label {
  font-size: var(--text-small);
  color: var(--text-disabled);
}
.st-ov-value {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}
.st-ov-value.success { color: var(--state-success); }
.st-ov-value.error   { color: var(--state-error); }

.st-ds {
  font-size: var(--text-body);
  color: var(--text-secondary);
}
</style>
