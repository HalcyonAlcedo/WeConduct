<script setup lang="ts">
import { t } from '@/i18n'
</script>

<template>
  <p class="npr-notice" role="alert">
    {{ t('framework.common.sensitivePlaintextWarning', '敏感信息建议使用加密参数。') }}
  </p>
</template>

<style scoped>
.npr-notice {
  margin: 0 0 var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--state-warning);
  border-radius: var(--radius-sm);
  background: rgba(232,152,104,0.10);
  color: var(--text-secondary);
  font-size: var(--text-caption);
  line-height: 1.45;
}
</style>
