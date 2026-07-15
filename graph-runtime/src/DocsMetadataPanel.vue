<script setup lang="ts">
import { computed } from 'vue'
import DocsMetadataValue from './DocsMetadataValue.vue'
import type { GraphNode } from './types'

const props = defineProps<{
  node: GraphNode
  collapsed: boolean
}>()

defineEmits<{
  toggle: []
}>()

const title = computed(() => props.node.display_name || props.node.node_kind || props.node.node_id)
const identityRows = computed(() => [
  ['节点 ID', props.node.node_id],
  ['资源类型', props.node.node_kind || '未声明'],
  ['节点类型', props.node.lowered_kind],
  ['展开角色', props.node.expansion_role || '未声明'],
  ['源码锚点', props.node.source_anchor_ref || '未声明'],
  ['位置', `x ${props.node.position.x} / y ${props.node.position.y}`],
])
</script>

<template>
  <aside
    :class="['wc-metadata-panel', { 'is-collapsed': collapsed }]"
    aria-label="节点元数据"
  >
    <button
      type="button"
      class="wc-meta-toggle"
      :title="collapsed ? '展开元数据' : '折叠元数据'"
      :aria-label="collapsed ? '展开元数据' : '折叠元数据'"
      @click="$emit('toggle')"
    >
      {{ collapsed ? '‹' : '›' }}
    </button>

    <template v-if="!collapsed">
      <header class="wc-meta-header">
        <p class="wc-meta-eyebrow">节点元数据</p>
        <h3 class="wc-meta-title">{{ title }}</h3>
      </header>

      <div class="wc-meta-body">
        <section class="wc-meta-section">
          <h4>身份</h4>
          <dl class="wc-meta-identity">
            <template v-for="([label, value]) in identityRows" :key="label">
              <dt>{{ label }}</dt>
              <dd>{{ value }}</dd>
            </template>
          </dl>
        </section>

        <section class="wc-meta-section">
          <h4>端口</h4>
          <p v-if="node.ports.length === 0" class="wc-meta-empty">无端口</p>
          <ul v-else class="wc-meta-ports">
            <li v-for="port in node.ports" :key="port.port_id" class="wc-meta-port">
              <div class="wc-meta-port-heading">
                <code>{{ port.port_id }}</code>
                <span>{{ port.direction === 'input' ? '输入' : '输出' }}</span>
                <span>{{ port.relation_layer }}</span>
              </div>
              <p v-if="port.semantic_slot">{{ port.semantic_slot }}</p>
              <p v-if="port.display_name">{{ port.display_name }}</p>
            </li>
          </ul>
        </section>

        <section class="wc-meta-section">
          <h4>配置</h4>
          <DocsMetadataValue name="node_config" :value="node.node_config || {}" />
        </section>
      </div>
    </template>
  </aside>
</template>
