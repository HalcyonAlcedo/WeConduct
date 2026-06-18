<script setup lang="ts">
import { useToastStore } from '@/stores/toastStore'

const toast = useToastStore()

function toastClass(type: string) {
  return {
    'toast': true,
    'toast-success': type === 'success',
    'toast-error': type === 'error',
    'toast-warning': type === 'warning',
    'toast-info': type === 'info',
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="toast-container" aria-live="polite">
      <div
        v-for="t in toast.toasts"
        :key="t.id"
        :class="toastClass(t.type)"
      >
        <div class="toast-body">
          <span class="toast-title">{{ t.title }}</span>
          <span v-if="t.message" class="toast-msg">{{ t.message }}</span>
        </div>
        <button class="toast-close" @click="toast.remove(t.id)">&times;</button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  bottom: 36px;
  right: 16px;
  z-index: 9999;
  display: flex;
  flex-direction: column-reverse;
  gap: 8px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 300px;
  max-width: 440px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  font-family: var(--font-ui);
  font-size: var(--text-body);
  box-shadow: var(--shadow-menu);
  pointer-events: auto;
  animation: toast-in 200ms var(--ease-out);
}

@keyframes toast-in {
  from { opacity: 0; transform: translateY(8px) scale(0.96); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.toast-success {
  background: #EDF7ED;
  border: 1px solid #B7E1B7;
  color: #2B5E2B;
}
.toast-error {
  background: #FDEDEC;
  border: 1px solid #F5C6CB;
  color: #7B2D2E;
}
.toast-warning {
  background: #FEF7EC;
  border: 1px solid #F5D8A8;
  color: #6B4C1C;
}
.toast-info {
  background: #EDF2F7;
  border: 1px solid #C5D3E8;
  color: #2C5282;
}

.toast-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.toast-title {
  font-weight: 600;
  font-size: var(--text-body);
}

.toast-msg {
  font-size: var(--text-small);
  opacity: 0.8;
}

.toast-close {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  cursor: pointer;
  opacity: 0.4;
  font-size: 16px;
  color: inherit;
  border-radius: var(--radius-sm);
}
.toast-close:hover { opacity: 0.8; }
</style>
