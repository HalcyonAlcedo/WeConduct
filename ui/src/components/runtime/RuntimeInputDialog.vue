<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRuntimeStore } from '@/stores/runtimeStore'
import { t } from '@/i18n'

const runtime = useRuntimeStore()
const formValues = reactive<Record<string, unknown>>({})
const password = ref('')
const errorMessage = ref('')
const submitting = ref(false)

const pendingInput = computed(() => runtime.pendingRuntimeInput)
const unlockSessionId = computed(() => runtime.pendingParameterUnlockSessionId)

watch(() => pendingInput.value?.request_id, () => {
  for (const key of Object.keys(formValues)) delete formValues[key]
  for (const field of pendingInput.value?.fields ?? []) {
    formValues[field.field_id] = field.value_type === 'boolean' ? false : ''
  }
  errorMessage.value = ''
})

watch(unlockSessionId, () => {
  password.value = ''
  errorMessage.value = ''
})

function normalizeValues(): Record<string, unknown> {
  const values: Record<string, unknown> = {}
  for (const field of pendingInput.value?.fields ?? []) {
    const value = formValues[field.field_id]
    values[field.field_id] = field.value_type === 'number' || field.value_type === 'integer'
      ? Number(value)
      : value
  }
  return values
}

async function submitInput() {
  submitting.value = true
  errorMessage.value = ''
  try {
    await runtime.submitPendingRuntimeInput(normalizeValues())
    for (const key of Object.keys(formValues)) formValues[key] = ''
  } catch (error: any) {
    errorMessage.value = error?.body?.message || error?.message || t('framework.runtimeInput.submitFailed', '输入提交失败')
  } finally {
    submitting.value = false
  }
}

async function unlock() {
  let submittedPassword = password.value
  password.value = ''
  submitting.value = true
  errorMessage.value = ''
  try {
    await runtime.unlockAndResumeRuntime(submittedPassword)
  } catch (error: any) {
    errorMessage.value = error?.body?.message || error?.message || t('framework.runtimeInput.unlockFailed', '参数解锁失败')
  } finally {
    submittedPassword = ''
    submitting.value = false
  }
}

async function abort() {
  await runtime.abortActiveRun('input_cancelled')
  errorMessage.value = ''
}
</script>

<template>
  <div v-if="pendingInput || unlockSessionId" class="rid-backdrop" role="presentation">
    <section class="rid-box" role="dialog" aria-modal="true" :aria-label="pendingInput ? t('framework.runtimeInput.title', '运行输入') : t('framework.runtimeInput.unlockTitle', '参数解锁')">
      <div class="rid-hd">{{ pendingInput ? t('framework.runtimeInput.title', '运行输入') : t('framework.runtimeInput.unlockTitle', '参数解锁') }}</div>
      <div class="rid-body">
        <template v-if="pendingInput">
          <form @submit.prevent="submitInput">
            <label v-for="field in pendingInput.fields" :key="field.field_id" class="rid-field">
              <span class="rid-field-label">{{ field.label }}<em v-if="field.required" class="rid-required">*</em></span>
              <input
                v-if="field.value_type === 'boolean'"
                v-model="formValues[field.field_id]"
                type="checkbox"
                :disabled="submitting"
                class="rid-check"
              >
              <input
                v-else
                v-model="formValues[field.field_id]"
                :type="field.sensitive ? 'password' : field.value_type === 'number' || field.value_type === 'integer' ? 'number' : 'text'"
                :required="field.required"
                :autocomplete="field.sensitive ? 'new-password' : 'off'"
                :disabled="submitting"
                class="rid-input"
              >
            </label>
            <p v-if="errorMessage" class="rid-error">{{ errorMessage }}</p>
            <div class="rid-actions">
              <button type="button" class="rid-btn" :disabled="submitting" @click="abort">{{ t('framework.runtimeInput.abort', '终止运行') }}</button>
              <button type="submit" class="rid-btn rid-btn-primary" :disabled="submitting">{{ submitting ? t('framework.runtimeInput.submitting', '提交中') : t('framework.runtimeInput.submit', '提交') }}</button>
            </div>
          </form>
        </template>
        <template v-else>
          <form @submit.prevent="unlock">
            <label class="rid-field">
              <span class="rid-field-label">{{ t('framework.runtimeInput.projectPassword', '项目参数密码') }}</span>
              <input v-model="password" type="password" class="rid-input" required autocomplete="current-password" :disabled="submitting">
            </label>
            <p v-if="errorMessage" class="rid-error">{{ errorMessage }}</p>
            <div class="rid-actions">
              <button type="button" class="rid-btn" :disabled="submitting" @click="abort">{{ t('framework.runtimeInput.abort', '终止运行') }}</button>
              <button type="submit" class="rid-btn rid-btn-primary" :disabled="submitting">{{ submitting ? t('framework.runtimeInput.unlocking', '解锁中') : t('framework.runtimeInput.unlockAndRun', '解锁并运行') }}</button>
            </div>
          </form>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.rid-backdrop {
  position: fixed; inset: 0; z-index: 1200;
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-xl);
  background: rgba(0,0,0,0.4);
}

.rid-box {
  width: min(440px, 100%);
  max-height: calc(100vh - 48px);
  overflow: auto;
  background: var(--bg-panel);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-menu);
}

.rid-hd {
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.rid-body {
  padding: var(--space-lg);
}

.rid-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-md);
}

.rid-field-label {
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.rid-required {
  margin-left: 4px;
  color: var(--state-error);
  font-style: normal;
}

.rid-input {
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-family: var(--font-ui);
  font-size: var(--text-body);
  min-height: 30px;
}

.rid-input:focus {
  border-color: var(--accent);
  outline: none;
}

.rid-check {
  justify-self: start;
  min-height: auto;
}

.rid-error {
  margin: 0 0 var(--space-sm);
  color: var(--state-error);
  font-size: var(--text-small);
}

.rid-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  margin-top: var(--space-lg);
}

.rid-btn {
  padding: var(--space-xs) var(--space-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  font-family: var(--font-ui);
  font-size: var(--text-body);
  cursor: pointer;
}

.rid-btn:hover:not(:disabled) {
  background: var(--bg-hover);
}

.rid-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.rid-btn-primary {
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
}

.rid-btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
}
</style>
