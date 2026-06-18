<script setup lang="ts">
import { ref } from 'vue'
import { postConvertWebcontrol, postFileDialog, postProjectOpen } from '@/services/api'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useRuntimeStore } from '@/stores/runtimeStore'
import { useResourceStore } from '@/stores/resourceStore'
import { useToastStore } from '@/stores/toastStore'
import type { WebControlConvertResponse } from '@/types/domains/api'

const emit = defineEmits<{ close: [] }>()
const workspace = useWorkspaceStore()
const graphWs = useGraphWorkspaceStore()
const runtime = useRuntimeStore()
const resource = useResourceStore()
const toast = useToastStore()

const sourcePath = ref('')
const blueprintFiles = ref<string[]>([])
const blueprintDir = ref('')
const outputPath = ref('')
const projectName = ref('')
const overwriteOutput = ref(false)
const autoOpen = ref(true)
const preserveLegacyMeta = ref(false)
const writeConversionReport = ref(true)

const loading = ref(false)
const result = ref<WebControlConvertResponse | null>(null)

async function pickFile(target: 'source' | 'output' | 'blueprintDir') {
  try {
    const mode = target === 'blueprintDir' ? 'open_folder' : target === 'output' ? 'save_file' : 'open_file'
    const r = await postFileDialog({ mode, title: target === 'source' ? '选择主流程文件' : target === 'output' ? '选择输出项目文件路径' : '选择蓝图目录' })
    if (r.status === 'selected' && r.paths.length) {
      if (target === 'source') sourcePath.value = r.paths[0]
      else if (target === 'output') outputPath.value = r.paths[0]
      else blueprintDir.value = r.paths[0]
    }
  } catch (e: any) {
    if (e?.status === 503) toast.info('', '当前运行环境不支持系统文件选择器')
  }
}

async function addBlueprintFile() {
  try {
    const r = await postFileDialog({ mode: 'open_file', title: '选择蓝图文件' })
    if (r.status === 'selected') {
      for (const p of r.paths) {
        if (!blueprintFiles.value.includes(p)) blueprintFiles.value.push(p)
      }
    }
  } catch (e: any) {
    if (e?.status === 503) toast.info('', '当前运行环境不支持系统文件选择器')
  }
}

function removeBlueprintFile(idx: number) { blueprintFiles.value.splice(idx, 1) }

async function doConvert() {
  if (!sourcePath.value) { toast.info('', '请选择主流程文件'); return }
  if (!outputPath.value) { toast.info('', '请选择输出项目路径'); return }
  loading.value = true
  result.value = null
  try {
    const r = await postConvertWebcontrol({
      source_path: sourcePath.value,
      blueprint_paths: blueprintFiles.value.length ? blueprintFiles.value : undefined,
      blueprint_directory: blueprintDir.value || undefined,
      output_project_path: outputPath.value,
      project_name: projectName.value || undefined,
      overwrite_output: overwriteOutput.value,
      auto_open_project: autoOpen.value,
      preserve_legacy_metadata: preserveLegacyMeta.value,
      write_conversion_report: writeConversionReport.value,
    })
    result.value = r
    toast.success('转换完成', r.message || r.status)
    if (autoOpen.value && r.project && r.graph_document) {
      try {
        await postProjectOpen({ project_path: r.project.project_file_path })
        await workspace.refreshSnapshot()
        await graphWs.loadGraph()
        if (graphWs.graphModel) await graphWs.syncSource()
        runtime.refreshAll()
        resource.refreshAll()
        toast.info('已打开', r.project.project_name)
      } catch (e: any) { toast.error('打开项目失败', e?.message) }
    }
  } catch (e: any) {
    const msg = e?.body?.message || e?.body?.error || e?.message || '转换失败'
    toast.error('转换失败', msg)
    result.value = e?.body || null
  }
  finally { loading.value = false }
}
</script>
<template>
  <Teleport to="body">
    <div class="wcc-overlay">
      <div class="wcc-box">
        <div class="wcc-hd">
          <span>转换 WebControl</span>
          <button class="wcc-close" @click="emit('close')">✕</button>
        </div>
        <div class="wcc-body">
          <div class="wcc-field">
            <label>主流程文件 <em>*</em></label>
            <div class="wcc-path-row">
              <input v-model="sourcePath" class="wcc-input" placeholder="选择 .xml / .yaml 主流程文件" />
              <button class="wcc-pick" @click="pickFile('source')">…</button>
            </div>
          </div>
          <div class="wcc-field">
            <label>蓝图文件</label>
            <div v-for="(f, i) in blueprintFiles" :key="i" class="wcc-path-row" style="margin-bottom:2px">
              <input class="wcc-input" :value="f" disabled />
              <button class="wcc-rm" @click="removeBlueprintFile(i)">✕</button>
            </div>
            <button class="wcc-add" @click="addBlueprintFile">+ 添加蓝图文件</button>
          </div>
          <div class="wcc-field">
            <label>蓝图目录</label>
            <div class="wcc-path-row">
              <input v-model="blueprintDir" class="wcc-input" placeholder="选择蓝图 XML 目录（可选）" />
              <button class="wcc-pick" @click="pickFile('blueprintDir')">📁</button>
            </div>
          </div>
          <div class="wcc-field">
            <label>输出项目路径 <em>*</em></label>
            <div class="wcc-path-row">
              <input v-model="outputPath" class="wcc-input" placeholder="输出 .weconduct.json 路径（必填）" />
              <button class="wcc-pick" @click="pickFile('output')">…</button>
            </div>
          </div>
          <div class="wcc-field">
            <label>项目名称</label>
            <input v-model="projectName" class="wcc-input" placeholder="默认按主流程命名" />
          </div>
          <div class="wcc-checks">
            <label class="wcc-chk"><input type="checkbox" v-model="overwriteOutput" /> 覆盖已有输出</label>
            <label class="wcc-chk"><input type="checkbox" v-model="autoOpen" /> 转换后自动打开项目</label>
            <label class="wcc-chk"><input type="checkbox" v-model="preserveLegacyMeta" /> 保留 legacy 元信息</label>
            <label class="wcc-chk"><input type="checkbox" v-model="writeConversionReport" /> 写出转换报告</label>
          </div>
        </div>
        <div class="wcc-ft">
          <button class="wcc-go" :disabled="loading || !sourcePath || !outputPath" @click="doConvert">
            {{ loading ? '转换中…' : '执行转换' }}
          </button>
        </div>
        <div v-if="result" class="wcc-result">
          <div class="wcc-r-hd">转换结果</div>
          <div class="wcc-r-grid" v-if="result.report">
            <div v-if="result.report.source_kind"><span>主流程类型</span><code>{{ result.report.source_kind }}</code></div>
            <div><span>主图节点</span><code>{{ result.report.main_graph_node_count ?? '—' }}</code></div>
            <div><span>主图边</span><code>{{ result.report.main_graph_edge_count ?? '—' }}</code></div>
            <div><span>蓝图导入</span><code>{{ result.report.imported_blueprint_count ?? '—' }}</code></div>
            <div><span>生成资源</span><code>{{ result.report.generated_resource_count ?? '—' }}</code></div>
            <div><span>Warning</span><code :class="result.report.warnings?.length ? 'wcc-warn' : ''">{{ result.report.warnings?.length ?? 0 }}</code></div>
            <div><span>Error</span><code :class="result.report.errors?.length ? 'wcc-err' : ''">{{ result.report.errors?.length ?? 0 }}</code></div>
          </div>
          <div v-if="result.report_path" class="wcc-r-path">报告: {{ result.report_path }}</div>
          <div v-if="result.message && !result.report" class="wcc-r-msg">{{ result.message }}</div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
<style scoped>
.wcc-overlay { position: fixed; inset: 0; z-index: 2000; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; }
.wcc-box { background: var(--bg-panel); border: 1px solid var(--border-default); border-radius: var(--radius-lg); min-width: 480px; max-width: 560px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: var(--shadow-menu); }
.wcc-hd { display: flex; align-items: center; padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--border-subtle); font-size: var(--text-body); font-weight: 600; color: var(--text-primary); flex-shrink: 0; }
.wcc-close { margin-left: auto; border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 12px; }
.wcc-body { padding: var(--space-md); overflow-y: auto; flex: 1; }
.wcc-field { margin-bottom: var(--space-sm); }
.wcc-field label { display: block; font-size: var(--text-small); color: var(--text-secondary); margin-bottom: 2px; }
.wcc-field label em { color: var(--state-error); font-style: normal; }
.wcc-path-row { display: flex; gap: 4px; }
.wcc-input { flex: 1; padding: 3px 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-small); }
.wcc-input:disabled { opacity: 0.6; }
.wcc-pick, .wcc-add, .wcc-rm { padding: 3px 8px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-small); }
.wcc-pick:hover, .wcc-add:hover { background: var(--bg-hover); }
.wcc-rm { color: var(--text-disabled); font-size: 10px; }
.wcc-rm:hover { color: var(--state-error); }
.wcc-add { margin-top: 2px; border-style: dashed; }
.wcc-checks { display: flex; flex-direction: column; gap: 3px; margin-top: var(--space-sm); }
.wcc-chk { display: flex; align-items: center; gap: 6px; font-size: var(--text-small); color: var(--text-secondary); cursor: pointer; }
.wcc-chk input { margin: 0; }
.wcc-ft { padding: var(--space-sm) var(--space-md); border-top: 1px solid var(--border-subtle); flex-shrink: 0; }
.wcc-go { width: 100%; padding: 6px; border: 1px solid var(--accent); border-radius: var(--radius-md); background: var(--accent); color: #fff; cursor: pointer; font-size: var(--text-body); font-family: var(--font-ui); font-weight: 600; }
.wcc-go:hover:not(:disabled) { background: var(--accent-hover); }
.wcc-go:disabled { opacity: 0.5; cursor: not-allowed; }
.wcc-result { padding: var(--space-sm) var(--space-md); border-top: 1px solid var(--border-subtle); background: var(--bg-input); flex-shrink: 0; }
.wcc-r-hd { font-size: var(--text-small); font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.wcc-r-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 8px; font-size: var(--text-small); }
.wcc-r-grid div { display: flex; justify-content: space-between; align-items: center; }
.wcc-r-grid span { color: var(--text-disabled); }
.wcc-r-grid code { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-primary); }
.wcc-warn { color: var(--state-warning) !important; font-weight: 600; }
.wcc-err { color: var(--state-error) !important; font-weight: 600; }
.wcc-r-path { margin-top: 4px; font-size: var(--text-caption); color: var(--text-disabled); font-family: var(--font-mono); }
.wcc-r-msg { font-size: var(--text-small); color: var(--text-secondary); }
</style>
