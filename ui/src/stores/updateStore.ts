import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchUpdateStatus, postUpdateCheck } from '@/services/api'
import type { UpdateStatusResponse } from '@/types/domains/api'

export const useUpdateStore = defineStore('update', () => {
  const status = ref<UpdateStatusResponse | null>(null)
  const isChecking = ref(false)
  const lastError = ref<string | null>(null)

  const updateAvailable = computed(() => !!status.value?.update_available)

  async function fetchStatus() {
    status.value = await fetchUpdateStatus()
    lastError.value = status.value.check_error
    return status.value
  }

  async function checkForUpdates(force: boolean) {
    isChecking.value = true
    try {
      status.value = await postUpdateCheck({ force })
      lastError.value = status.value.check_error
      return status.value
    } finally {
      isChecking.value = false
    }
  }

  return {
    status,
    isChecking,
    lastError,
    updateAvailable,
    fetchStatus,
    checkForUpdates,
  }
})
