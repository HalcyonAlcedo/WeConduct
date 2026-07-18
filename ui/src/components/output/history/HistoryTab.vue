<script setup lang="ts">
import { computed, ref } from 'vue'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import PlaceholderBanner from '@/components/common/PlaceholderBanner.vue'
import { t } from '@/i18n'

const workspace = useWorkspaceStore()

const history = computed(() => workspace.compileHistory ?? [])
const expandedSeq = ref<number | null>(null)

function toggleExpand(seq: number) {
  expandedSeq.value = expandedSeq.value === seq ? null : seq
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch { return iso.slice(0, 19) }
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms}ms`
}

function statusClass(status: string) {
  switch (status) {
    case 'succeeded': return 'hs-success'
    case 'failed': return 'hs-error'
    case 'unsupported': return 'hs-warning'
    default: return ''
  }
}

function statusLabel(status: string) {
  switch (status) {
    case 'succeeded': return t('framework.history.status.succeeded', '成功')
    case 'failed': return t('framework.history.status.failed', '失败')
    case 'unsupported': return t('framework.history.status.unsupported', '不支持')
    default: return status
  }
}

function stageStatusClass(status: string) {
  switch (status) {
    case 'succeeded': return 'ss-success'
    case 'failed': return 'ss-error'
    default: return 'ss-pending'
  }
}

function highestSeverity(item: typeof history.value[0]): string | null {
  return item.diagnostic_summary?.highest_severity ?? null
}
</script>

<template>
  <div class="history-tab">
    <PlaceholderBanner
      v-if="history.length === 0"
      type="empty"
      :title="t('framework.history.empty.title', '暂无编译记录')"
      :description="t('framework.history.empty.description', '运行编译后在此查看历史记录')"
    />

    <div v-else class="ht-scroll">
      <table class="ht-table">
        <thead>
          <tr>
            <th class="col-exp"></th>
            <th class="col-time">{{ t('framework.history.table.time', '时间') }}</th>
            <th class="col-seq">#</th>
            <th class="col-status">{{ t('framework.history.table.status', '状态') }}</th>
            <th class="col-kind">{{ t('framework.history.table.kind', '类型') }}</th>
            <th class="col-diag">{{ t('framework.history.table.diagnostics', '诊断') }}</th>
            <th class="col-graph">{{ t('framework.history.table.graph', '图') }}</th>
            <th class="col-dur">{{ t('framework.history.table.duration', '耗时') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="item in history" :key="item.request_sequence">
            <tr
              class="ht-row"
              :class="{ 'ht-expanded': expandedSeq === item.request_sequence }"
              @click="toggleExpand(item.request_sequence)"
            >
              <td class="col-exp">
                <span class="ht-exp-arrow">{{ expandedSeq === item.request_sequence ? '▾' : '▸' }}</span>
              </td>
              <td class="col-time">{{ formatTime(item.compiled_at) }}</td>
              <td class="col-seq">{{ item.request_sequence }}</td>
              <td>
                <span :class="['ht-badge', statusClass(item.status)]">
                  {{ statusLabel(item.status) }}
                </span>
              </td>
              <td class="col-kind">{{ item.source_kind }}</td>
              <td class="col-diag">
                {{ item.diagnostic_summary?.total_count ?? 0 }}
                <span v-if="highestSeverity(item)" class="ht-sev">({{ highestSeverity(item) }})</span>
              </td>
              <td class="col-graph">
                {{ item.graph_stats?.node_count ?? 0 }}N / {{ item.graph_stats?.edge_count ?? 0 }}E
              </td>
              <td class="col-dur">{{ formatDuration(item.duration_ms ?? null) }}</td>
            </tr>
            <tr v-if="expandedSeq === item.request_sequence" class="ht-detail-row">
              <td colspan="8">
                <div class="ht-detail">
                  <div class="ht-detail-section">
                    <h4 class="ht-detail-head">{{ t('framework.history.detail.stagesTitle', '阶段明细') }}</h4>
                    <div class="ht-stage-cards">
                      <div
                        v-for="card in item.stage_cards"
                        :key="card.stage"
                        class="ht-stage-item"
                      >
                        <span :class="['ht-stage-dot', stageStatusClass(card.status)]"></span>
                        <span class="ht-stage-name">{{ card.stage }}</span>
                        <span class="ht-stage-diag">{{ t('framework.history.detail.stageDiag', '{n} 诊断', { n: card.diagnostic_count }) }}</span>
                      </div>
                    </div>
                  </div>
                  <div class="ht-detail-grid">
                    <div class="ht-detail-section">
                      <h4 class="ht-detail-head">{{ t('framework.history.detail.overviewTitle', '概要') }}</h4>
                      <div class="ht-detail-meta">
                        <span>{{ t('framework.history.detail.totalStages', '总阶段') }}: {{ item.stage_overview.total_stage_count }}</span>
                        <span>{{ t('framework.history.detail.succeeded', '成功') }}: {{ item.stage_overview.succeeded_stage_count }}</span>
                        <span v-if="item.stage_overview.failed_stage_count">{{ t('framework.history.detail.failed', '失败') }}: {{ item.stage_overview.failed_stage_count }}</span>
                        <span v-if="item.stage_overview.terminal_stage">{{ t('framework.history.detail.terminal', '终止') }}: {{ item.stage_overview.terminal_stage }}</span>
                      </div>
                    </div>
                    <div class="ht-detail-section" v-if="item.primary_diagnostic">
                      <h4 class="ht-detail-head">{{ t('framework.history.detail.primaryTitle', '主要诊断') }}</h4>
                      <div class="ht-detail-meta">
                        <span>{{ t('framework.history.detail.stage', '阶段') }}: {{ item.primary_diagnostic.stage }}</span>
                        <span>{{ t('framework.history.detail.category', '类别') }}: {{ item.primary_diagnostic.category }}</span>
                        <span>{{ t('framework.history.detail.severity', '严重度') }}: {{ item.primary_diagnostic.severity }}</span>
                      </div>
                      <p class="ht-detail-msg">{{ item.primary_diagnostic.message }}</p>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.history-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.ht-scroll {
  flex: 1;
  overflow-y: auto;
}

.ht-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-body);
}
.ht-table th {
  text-align: left;
  padding: 5px 8px;
  background: var(--bg-panel-header);
  color: var(--text-disabled);
  font-weight: 600;
  font-size: var(--text-small);
  border-bottom: 1px solid var(--border-subtle);
  position: sticky;
  top: 0;
  z-index: 1;
}
.ht-table td {
  padding: 4px 8px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}

.col-exp { width: 22px; text-align: center; }
.col-time { width: 100px; font-size: var(--text-small); }
.col-seq { width: 32px; font-family: var(--font-mono); font-size: var(--text-small); }
.col-status { width: 56px; }
.col-kind { width: 110px; font-family: var(--font-mono); font-size: var(--text-small); }
.col-diag { width: 70px; font-size: var(--text-small); }
.col-graph { width: 70px; font-size: var(--text-small); }
.col-dur { width: 60px; font-size: var(--text-small); color: var(--text-disabled); }

.ht-row { cursor: pointer; transition: background 80ms; }
.ht-row:hover { background: var(--bg-hover); }
.ht-row.ht-expanded { background: var(--bg-selected); }

.ht-exp-arrow { font-size: 10px; color: var(--text-disabled); }

.ht-badge {
  display: inline-block;
  padding: 1px 5px;
  border-radius: var(--radius-sm);
  font-size: var(--text-caption);
  font-weight: 600;
}
.hs-success { background: rgba(107,154,102,0.12); color: var(--state-success); }
.hs-error   { background: rgba(208,112,96,0.12); color: var(--state-error); }
.hs-warning { background: rgba(200,148,74,0.12); color: var(--state-degraded); }

.ht-sev { font-size: var(--text-caption); color: var(--text-disabled); }

.ht-detail-row td { padding: 0; border-bottom: 2px solid var(--border-subtle); }
.ht-detail { padding: var(--space-md) var(--space-lg); background: var(--bg-input); display: flex; flex-direction: column; gap: var(--space-md); }

.ht-detail-section { flex: 1; }
.ht-detail-head { font-size: var(--text-small); font-weight: 600; color: var(--text-secondary); margin-bottom: var(--space-xs); }

.ht-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-md); }

.ht-stage-cards { display: flex; flex-wrap: wrap; gap: var(--space-sm); }
.ht-stage-item { display: flex; align-items: center; gap: 4px; font-size: var(--text-small); }
.ht-stage-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.ss-success { background: var(--state-success); }
.ss-error   { background: var(--state-error); }
.ss-pending { background: var(--text-disabled); opacity: 0.4; }
.ht-stage-name { font-family: var(--font-mono); font-size: var(--text-caption); }
.ht-stage-diag { font-size: var(--text-caption); color: var(--text-disabled); }

.ht-detail-meta { display: flex; flex-wrap: wrap; gap: var(--space-sm); font-size: var(--text-small); color: var(--text-secondary); }
.ht-detail-msg { font-size: var(--text-small); color: var(--text-primary); margin-top: var(--space-xs); margin-bottom: 0; }
</style>
