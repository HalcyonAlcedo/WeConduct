<script setup lang="ts">
/** Five-state visual distinction system — the critical design rule.
 *  Uses border style + background + icon + text to encode state.
 */
export type BannerType = 'empty' | 'unimplemented' | 'notready' | 'failure' | 'degraded'

defineProps<{
  type: BannerType
  title: string
  description?: string
}>()
</script>

<template>
  <div :class="['placeholder', `ph-${type}`]" role="status">
    <span class="ph-icon">
      <template v-if="type === 'empty'">○</template>
      <template v-else-if="type === 'unimplemented'">🔧</template>
      <template v-else-if="type === 'notready'">🔌</template>
      <template v-else-if="type === 'failure'">✕</template>
      <template v-else-if="type === 'degraded'">⚠</template>
    </span>
    <div class="ph-text">
      <span class="ph-title">{{ title }}</span>
      <span v-if="description" class="ph-desc">{{ description }}</span>
    </div>
  </div>
</template>

<style scoped>
.placeholder {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-lg) var(--space-xl);
  margin: var(--space-lg);
  border-radius: var(--radius-md);
  font-family: var(--font-ui);
}

/* Empty data — dashed border, gray */
.ph-empty {
  border: 1px dashed var(--border-default);
  background: var(--placeholder-empty);
}

/* Not implemented — solid border + diagonal stripes, amber */
.ph-unimplemented {
  border: 1px solid #E8C89A;
  background: var(--placeholder-unimplemented);
  background-image: repeating-linear-gradient(
    45deg,
    transparent,
    transparent 8px,
    rgba(232, 200, 154, 0.12) 8px,
    rgba(232, 200, 154, 0.12) 10px
  );
}

/* Interface not ready — dotted border, violet */
.ph-notready {
  border: 1.5px dotted #B8A0D0;
  background: var(--placeholder-notready);
}

/* Current failure — solid red border, red */
.ph-failure {
  border: 1.5px solid var(--state-error);
  background: var(--placeholder-failure);
}

/* Degraded — solid amber border, yellow */
.ph-degraded {
  border: 1px solid var(--state-degraded);
  background: var(--placeholder-degraded);
}

.ph-icon {
  font-size: 20px;
  flex-shrink: 0;
  opacity: 0.7;
}

.ph-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ph-title {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.ph-desc {
  font-size: var(--text-small);
  color: var(--text-secondary);
}
</style>
