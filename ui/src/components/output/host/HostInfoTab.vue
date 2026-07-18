<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchHostInfo } from '@/services/api'
import PlaceholderBanner from '@/components/common/PlaceholderBanner.vue'
import type { HostInfoResponse } from '@/types/domains/api'
import { t } from '@/i18n'

const loading = ref(false)
const info = ref<HostInfoResponse | null>(null)
const error = ref<string | null>(null)

async function load() {
  loading.value = true; error.value = null
  try { info.value = await fetchHostInfo() }
  catch (err: any) { error.value = err?.message ?? t('framework.hostInfo.loadFailed', '加载失败') }
  finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div class="hi-tab">
    <div v-if="loading" class="loading"><div class="sk skeleton-pulse"></div></div>
    <PlaceholderBanner v-if="error" type="failure" :title="error ?? t('framework.hostInfo.loadFailed', '加载失败')" />
    <template v-if="info">
      <div class="hi-section">
        <h4>{{ t('framework.hostInfo.host.title', '宿主信息') }}</h4>
        <div class="hi-grid">
          <span>{{ t('framework.hostInfo.host.mode', '模式') }}: <code>{{ info.host_mode }}</code></span>
          <span>API: <code>{{ info.api_version }}</code></span>
          <span>{{ t('framework.hostInfo.host.bind', '绑定') }}: <code>{{ info.server_bind.host }}:{{ info.server_bind.port }}</code></span>
          <span>URL: <code>{{ info.server_bind.base_url }}</code></span>
        </div>
      </div>
      <div class="hi-section">
        <h4>{{ t('framework.hostInfo.uiHosting.title', 'UI 托管') }}</h4>
        <div class="hi-grid">
          <span>{{ t('framework.hostInfo.uiHosting.hosted', '已托管') }}: {{ info.ui_hosting.ui_hosted ? t('framework.hostInfo.yes', '是') : t('framework.hostInfo.no', '否') }}</span>
          <span>{{ t('framework.hostInfo.uiHosting.distAvailable', '产物可用') }}: {{ info.ui_hosting.ui_dist_available ? t('framework.hostInfo.yes', '是') : t('framework.hostInfo.no', '否') }}</span>
          <span>{{ t('framework.hostInfo.uiHosting.path', '路径') }}: <code>{{ info.ui_hosting.ui_dist_path }}</code></span>
          <span>{{ t('framework.hostInfo.uiHosting.entrypoint', '入口') }}: <code>{{ info.ui_hosting.ui_entrypoint ?? '—' }}</code></span>
        </div>
      </div>
      <div class="hi-section">
        <h4>{{ t('framework.hostInfo.manifest.title', '发布清单') }}</h4>
        <div class="hi-grid">
          <span>{{ t('framework.hostInfo.manifest.version', '版本') }}: <code>{{ info.release_manifest.manifest_version }}</code></span>
          <span>{{ t('framework.hostInfo.manifest.startup', '启动') }}: <code>{{ info.release_manifest.startup_command }}</code></span>
          <span>{{ t('framework.hostInfo.manifest.statePath', '状态路径') }}: <code>{{ info.release_manifest.workspace_state_path }}</code></span>
          <span>{{ t('framework.hostInfo.manifest.uiDist', 'UI 产物') }}: <code>{{ info.release_manifest.ui_dist_path }}</code></span>
        </div>
      </div>
      <button class="hi-btn" @click="load" :disabled="loading">{{ t('framework.hostInfo.refresh', '刷新') }}</button>
    </template>
  </div>
</template>

<style scoped>
.hi-tab { padding: var(--space-lg); }
.loading { padding: var(--space-lg); }
.sk { height: 40px; background: var(--bg-panel-header); border-radius: var(--radius-sm); }
.hi-section { margin-bottom: var(--space-xl); }
.hi-section h4 { font-size: var(--text-small); font-weight: 600; color: var(--text-secondary); margin-bottom: var(--space-xs); border-bottom: 1px solid var(--border-subtle); padding-bottom: var(--space-xs); }
.hi-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-xs); font-size: var(--text-small); color: var(--text-secondary); }
.hi-grid code { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-primary); background: var(--bg-input); padding: 1px 4px; border-radius: 2px; }
.hi-btn { margin-top: var(--space-md); padding: 4px 14px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-primary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-body); font-family: var(--font-ui); }
.hi-btn:hover:not(:disabled) { background: var(--bg-hover); }
.hi-btn:disabled { opacity: 0.4; }
</style>
