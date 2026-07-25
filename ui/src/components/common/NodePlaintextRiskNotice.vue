<template>
  <p class="node-plaintext-risk-notice" role="alert">
    节点配置会随项目保存。请优先使用待输入或加密初始参数；直接保存明文认证信息仅适用于特殊需求。
  </p>
</template>

<style scoped>
.node-plaintext-risk-notice {
  margin: 0 0 var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--state-warning);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--state-warning) 10%, transparent);
  color: var(--text-secondary);
  font-size: var(--text-caption);
  line-height: 1.45;
}
</style>
