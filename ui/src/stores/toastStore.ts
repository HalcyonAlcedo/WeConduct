/** WeConduct — Toast Notification Store
 *  Non-modal notifications for compile outcomes and system events.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface Toast {
  id: number
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  message?: string
  durationMs: number
}

let nextId = 0

export const useToastStore = defineStore('toast', () => {
  const toasts = ref<Toast[]>([])

  function add(type: Toast['type'], title: string, message?: string, durationMs = 4000) {
    const id = ++nextId
    toasts.value.push({ id, type, title, message, durationMs })
    if (durationMs > 0) {
      setTimeout(() => remove(id), durationMs)
    }
  }

  function remove(id: number) {
    const idx = toasts.value.findIndex(t => t.id === id)
    if (idx >= 0) toasts.value.splice(idx, 1)
  }

  function success(title: string, message?: string) {
    add('success', title, message, 3000)
  }

  function error(title: string, message?: string) {
    add('error', title, message, 5000)
  }

  function warning(title: string, message?: string) {
    add('warning', title, message, 4000)
  }

  function info(title: string, message?: string) {
    add('info', title, message, 3000)
  }

  return { toasts, add, remove, success, error, warning, info }
})
