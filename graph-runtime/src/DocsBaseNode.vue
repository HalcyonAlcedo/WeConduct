<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import type { DocsNodeData, GraphPort } from './types'

const props = defineProps<{
  id: string
  data: DocsNodeData
  selected?: boolean
}>()

const inputPorts = computed(() => props.data.ports.filter(port => port.direction === 'input'))
const outputPorts = computed(() => props.data.ports.filter(port => port.direction === 'output'))
const kindClass = computed(() => `node-${props.data.kind}`)
const kindLabel = computed(() => {
  switch (props.data.kind) {
    case 'execution': return '执行'
    case 'control': return '控制'
    case 'observe': return '观察'
    case 'bridge': return '桥接'
    default: return props.data.kind
  }
})

interface ConfigRow {
  key: string
  path: string
  display: string
}

interface ConfigSection {
  section?: string
  rows: ConfigRow[]
}

const configSections = computed<ConfigSection[]>(() => {
  const sections: ConfigSection[] = []
  for (const [key, value] of Object.entries(props.data.nodeConfig)) {
    if (isPlainObject(value)) {
      sections.push({
        section: key,
        rows: Object.entries(value).map(([childKey, childValue]) => ({
          key: childKey,
          path: `${key}.${childKey}`,
          display: formatValue(childValue),
        })),
      })
    } else {
      sections.push({ rows: [{ key, path: key, display: formatValue(value) }] })
    }
  }
  return sections
})

function portLabel(port: GraphPort): string {
  const value = port.display_name || port.semantic_slot || port.port_id
  return value
    .replace(/\.(in|out)$/, '')
    .replace(/^(in|out)\./, '')
    .replace(/\.(in|out)\./, '.')
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function formatValue(value: unknown): string {
  if (typeof value === 'string') return value.slice(0, 30)
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    const labels = value
      .filter(item => isPlainObject(item) && typeof item.label === 'string')
      .map(item => String(item.label))
      .slice(0, 3)
    return labels.length
      ? `${labels.join(', ')}${value.length > 3 ? ` …(${value.length})` : ` (${value.length})`}`
      : `(${value.length} items)`
  }
  if (isPlainObject(value)) return `(${Object.keys(value).length} keys)`
  if (value === null) return 'null'
  return `(${typeof value})`
}
</script>

<template>
  <div :class="['vf-node', kindClass, { selected }]">
    <div class="vf-node-header">
      <span class="vf-node-kind">{{ kindLabel }}</span>
      <span v-if="data.nodeId" class="vf-node-id">{{ data.nodeId }}</span>
    </div>

    <div class="vf-node-row">
      <div v-if="inputPorts.length" class="vf-port-col">
        <div v-for="port in inputPorts" :key="port.port_id" class="vf-port-item">
          <Handle type="target" :position="Position.Left" :id="port.port_id" class="vf-handle" />
          <span class="vf-port-label">{{ portLabel(port) }}</span>
        </div>
      </div>

      <div class="vf-node-main">
        <div class="vf-node-body">
          <span class="vf-node-label">{{ data.label }}</span>
          <div v-if="configSections.length" class="vf-config">
            <template v-for="(section, sectionIndex) in configSections" :key="sectionIndex">
              <div v-if="section.section" class="vf-cfg-section">{{ section.section }}</div>
              <div v-for="row in section.rows" :key="row.path" class="vf-cfg-row">
                <span class="vf-cfg-key">{{ row.key }}</span>
                <span class="vf-cfg-ro">{{ row.display }}</span>
              </div>
            </template>
          </div>
        </div>
      </div>

      <div v-if="outputPorts.length" class="vf-port-col">
        <div v-for="port in outputPorts" :key="port.port_id" class="vf-port-item">
          <span class="vf-port-label">{{ portLabel(port) }}</span>
          <Handle type="source" :position="Position.Right" :id="port.port_id" class="vf-handle" />
        </div>
      </div>
    </div>

    <template v-if="!data.ports.length">
      <Handle type="target" :position="Position.Left" class="vf-handle vf-no-port" />
      <Handle type="source" :position="Position.Right" class="vf-handle vf-no-port" />
    </template>
  </div>
</template>
