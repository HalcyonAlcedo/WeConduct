<script setup lang="ts">
import { computed } from 'vue'

defineOptions({ name: 'DocsMetadataValue' })

const props = withDefaults(defineProps<{
  name: string
  value: unknown
  depth?: number
}>(), {
  depth: 0,
})

const isArray = computed(() => Array.isArray(props.value))
const isObject = computed(() => (
  props.value !== null && typeof props.value === 'object' && !isArray.value
))
const isComposite = computed(() => isArray.value || isObject.value)
const entries = computed<[string, unknown][]>(() => {
  if (isArray.value) {
    return (props.value as unknown[]).map((value, index) => [String(index), value])
  }
  if (isObject.value) {
    return Object.entries(props.value as Record<string, unknown>)
  }
  return []
})
const typeLabel = computed(() => {
  if (props.value === null) return 'null'
  if (isArray.value) return 'array'
  return typeof props.value
})
const summary = computed(() => {
  if (isArray.value) return `${entries.value.length} 项`
  if (isObject.value) return `${entries.value.length} 个字段`
  return ''
})
const displayValue = computed(() => {
  if (props.value === null) return 'null'
  if (typeof props.value === 'string') return props.value || '""'
  if (typeof props.value === 'number' || typeof props.value === 'boolean') return String(props.value)
  if (typeof props.value === 'undefined') return 'undefined'
  return String(props.value)
})
</script>

<template>
  <div class="wc-meta-tree-item">
    <details v-if="isComposite" class="wc-meta-tree-group" :open="depth < 2">
      <summary>
        <span class="wc-meta-tree-key">{{ name }}</span>
        <span class="wc-meta-tree-type">{{ typeLabel }}</span>
        <span class="wc-meta-tree-count">{{ summary }}</span>
      </summary>
      <div class="wc-meta-tree-children">
        <DocsMetadataValue
          v-for="([entryName, entryValue]) in entries"
          :key="entryName"
          :name="entryName"
          :value="entryValue"
          :depth="depth + 1"
        />
        <p v-if="entries.length === 0" class="wc-meta-tree-empty">空</p>
      </div>
    </details>
    <div v-else class="wc-meta-tree-row">
      <span class="wc-meta-tree-key">{{ name }}</span>
      <span class="wc-meta-tree-value">{{ displayValue }}</span>
      <span class="wc-meta-tree-type">{{ typeLabel }}</span>
    </div>
  </div>
</template>
