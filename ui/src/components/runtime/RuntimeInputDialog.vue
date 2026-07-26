<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRuntimeStore } from '@/stores/runtimeStore'

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
    errorMessage.value = error?.body?.message || error?.message || '输入提交失败'
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
    errorMessage.value = error?.body?.message || error?.message || '参数解锁失败'
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
  <div v-if="pendingInput || unlockSessionId" class="runtime-input-backdrop" role="presentation">
    <section class="runtime-input-dialog" role="dialog" aria-modal="true" :aria-label="pendingInput ? '运行输入' : '参数解锁'">
      <template v-if="pendingInput">
        <h2>运行输入</h2>
        <form @submit.prevent="submitInput">
          <label v-for="field in pendingInput.fields" :key="field.field_id" class="runtime-input-field">
            <span>{{ field.label }}<em v-if="field.required">*</em></span>
            <input
              v-if="field.value_type === 'boolean'"
              v-model="formValues[field.field_id]"
              type="checkbox"
              :disabled="submitting"
            >
            <input
              v-else
              v-model="formValues[field.field_id]"
              :type="field.sensitive ? 'password' : field.value_type === 'number' || field.value_type === 'integer' ? 'number' : 'text'"
              :required="field.required"
              :autocomplete="field.sensitive ? 'new-password' : 'off'"
              :disabled="submitting"
            >
          </label>
          <p v-if="errorMessage" class="runtime-input-error">{{ errorMessage }}</p>
          <footer>
            <button type="button" :disabled="submitting" @click="abort">终止运行</button>
            <button type="submit" :disabled="submitting">{{ submitting ? '提交中' : '提交' }}</button>
          </footer>
        </form>
      </template>
      <template v-else>
        <h2>参数解锁</h2>
        <form @submit.prevent="unlock">
          <label class="runtime-input-field">
            <span>项目参数密码</span>
            <input v-model="password" type="password" required autocomplete="current-password" :disabled="submitting">
          </label>
          <p v-if="errorMessage" class="runtime-input-error">{{ errorMessage }}</p>
          <footer>
            <button type="button" :disabled="submitting" @click="abort">终止运行</button>
            <button type="submit" :disabled="submitting">{{ submitting ? '解锁中' : '解锁并运行' }}</button>
          </footer>
        </form>
      </template>
    </section>
  </div>
</template>

<style scoped>
.runtime-input-backdrop { position: fixed; inset: 0; z-index: 1200; display: grid; place-items: center; padding: 24px; background: rgb(14 18 24 / 62%); }
.runtime-input-dialog { width: min(440px, 100%); max-height: calc(100vh - 48px); overflow: auto; padding: 20px; border: 1px solid var(--border-color, #3a4656); border-radius: 6px; background: var(--panel-bg, #1e2630); color: var(--text-primary, #f2f5f8); box-shadow: 0 20px 56px rgb(0 0 0 / 38%); }
h2 { margin: 0 0 16px; font-size: 18px; font-weight: 600; }
.runtime-input-field { display: grid; gap: 7px; margin: 0 0 14px; font-size: 13px; }
.runtime-input-field span { color: var(--text-secondary, #b4c0cc); }
em { margin-left: 4px; color: #e05d58; font-style: normal; }
input { min-height: 34px; box-sizing: border-box; border: 1px solid var(--border-color, #4b5969); border-radius: 4px; padding: 6px 8px; background: var(--input-bg, #121820); color: inherit; }
input[type='checkbox'] { min-height: auto; justify-self: start; }
footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
button { min-height: 32px; border: 1px solid var(--border-color, #4b5969); border-radius: 4px; padding: 0 12px; background: transparent; color: inherit; cursor: pointer; }
button[type='submit'] { border-color: #2d9b7a; background: #17765d; }
button:disabled { opacity: .55; cursor: default; }
.runtime-input-error { margin: 0; color: #ef7770; font-size: 13px; }
</style>
