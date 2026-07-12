<script setup lang="ts">
import { computed } from 'vue'

defineOptions({ name: 'DebugValueTree' })

const props = withDefaults(defineProps<{
  label?: string
  value: unknown
  depth?: number
  expanded?: boolean
}>(), {
  label: '',
  depth: 0,
  expanded: false,
})

const isArray = computed(() => Array.isArray(props.value))
const isObject = computed(() => props.value !== null && typeof props.value === 'object')
const isComplex = computed(() => isArray.value || isObject.value)
const entries = computed(() => {
  if (!isComplex.value || props.depth >= 8) return []
  return Object.entries(props.value as Record<string, unknown>)
})
const typeLabel = computed(() => {
  if (props.value === null) return 'null'
  if (isArray.value) return `array(${(props.value as unknown[]).length})`
  if (isObject.value) return `object(${entries.value.length})`
  return typeof props.value
})
const scalarText = computed(() => {
  if (props.value === null) return 'null'
  if (typeof props.value === 'string') return props.value || '""'
  if (typeof props.value === 'undefined') return 'undefined'
  return String(props.value)
})
</script>

<template>
  <details v-if="isComplex && depth < 8" class="dvt-branch" :open="expanded || depth === 0">
    <summary>
      <span v-if="label" class="dvt-key">{{ label }}</span>
      <span class="dvt-type">{{ typeLabel }}</span>
    </summary>
    <div class="dvt-children">
      <DebugValueTree
        v-for="([childKey, childValue], index) in entries"
        :key="`${childKey}-${index}`"
        :label="isArray ? `[${childKey}]` : childKey"
        :value="childValue"
        :depth="depth + 1"
      />
      <span v-if="!entries.length" class="dvt-empty">空</span>
    </div>
  </details>
  <div v-else class="dvt-scalar">
    <span v-if="label" class="dvt-key">{{ label }}</span>
    <span class="dvt-type">{{ typeLabel }}</span>
    <span class="dvt-value">{{ isComplex ? typeLabel : scalarText }}</span>
  </div>
</template>

<style scoped>
.dvt-branch, .dvt-scalar { min-width: 0; font-family: var(--font-mono); font-size: var(--text-caption); }
.dvt-branch > summary { min-height: 24px; display: flex; align-items: center; gap: var(--space-xs); cursor: pointer; color: var(--text-primary); }
.dvt-children { margin-left: var(--space-sm); padding-left: var(--space-sm); border-left: 1px solid var(--border-subtle); }
.dvt-scalar { min-height: 24px; display: grid; grid-template-columns: minmax(80px, 0.45fr) auto minmax(80px, 1fr); align-items: center; gap: var(--space-sm); }
.dvt-key { overflow-wrap: anywhere; color: var(--text-primary); }
.dvt-type { color: var(--text-disabled); font-size: 10px; }
.dvt-value { overflow-wrap: anywhere; white-space: pre-wrap; color: var(--text-secondary); }
.dvt-empty { color: var(--text-disabled); }
</style>
