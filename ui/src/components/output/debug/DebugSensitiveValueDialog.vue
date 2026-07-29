<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDebugStore } from '@/stores/debugStore'
import { t } from '@/i18n'

const debug = useDebugStore()
const password = ref('')
const errorMessage = ref('')
const submitting = ref(false)
const pending = computed(() => debug.pendingSensitiveValueReveal)

watch(pending, () => {
  password.value = ''
  errorMessage.value = ''
})

async function reveal() {
  let submittedPassword = password.value
  password.value = ''
  submitting.value = true
  errorMessage.value = ''
  try {
    await debug.revealPendingSensitiveValue(submittedPassword)
  } catch (error: any) {
    errorMessage.value = error?.body?.message || error?.message || t('framework.debug.sensitiveReveal.failed', '敏感变量查看失败')
  } finally {
    submittedPassword = ''
    submitting.value = false
  }
}

function cancel() {
  debug.clearRevealedSensitiveValues()
}
</script>

<template>
  <div v-if="pending" class="dsd-backdrop" role="presentation">
    <section class="dsd-box" role="dialog" aria-modal="true" :aria-label="t('framework.debug.sensitiveReveal.title', '查看敏感变量')">
      <header class="dsd-hd">{{ t('framework.debug.sensitiveReveal.title', '查看敏感变量') }}</header>
      <form class="dsd-body" @submit.prevent="reveal">
        <p class="dsd-note">{{ t('framework.debug.sensitiveReveal.note', '敏感值仅在当前暂停的内存中显示，不会写入调试记录或日志。') }}</p>
        <label class="dsd-field">
          <span>{{ t('framework.debug.sensitiveReveal.password', '项目参数密码') }}</span>
          <input v-model="password" type="password" required autocomplete="current-password" :disabled="submitting">
        </label>
        <p v-if="errorMessage" class="dsd-error">{{ errorMessage }}</p>
        <footer class="dsd-actions">
          <button type="button" :disabled="submitting" @click="cancel">{{ t('framework.common.cancel', '取消') }}</button>
          <button type="submit" class="dsd-primary" :disabled="submitting">{{ submitting ? t('framework.debug.sensitiveReveal.verifying', '验证中') : t('framework.debug.sensitiveReveal.confirm', '验证并查看') }}</button>
        </footer>
      </form>
    </section>
  </div>
</template>

<style scoped>
.dsd-backdrop { position: fixed; inset: 0; z-index: 1210; display: grid; place-items: center; padding: var(--space-xl); background: rgba(0, 0, 0, .4); }
.dsd-box { width: min(420px, 100%); background: var(--bg-panel); border: 1px solid var(--border-default); border-radius: var(--radius-lg); box-shadow: var(--shadow-menu); }
.dsd-hd { padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--border-subtle); font-weight: 600; }
.dsd-body { display: grid; gap: var(--space-sm); padding: var(--space-md); }
.dsd-note { margin: 0; color: var(--text-secondary); font-size: var(--text-caption); line-height: 1.5; }
.dsd-field { display: grid; gap: var(--space-xs); font-size: var(--text-caption); }
.dsd-field input { width: 100%; padding: var(--space-xs) var(--space-sm); border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); }
.dsd-error { margin: 0; color: var(--state-error); font-size: var(--text-caption); }
.dsd-actions { display: flex; justify-content: flex-end; gap: var(--space-xs); }
.dsd-actions button { padding: 4px 10px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); cursor: pointer; }
.dsd-actions .dsd-primary { border-color: var(--accent); background: var(--accent); color: var(--text-on-accent); }
</style>
