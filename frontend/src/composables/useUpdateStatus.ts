import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, type UpdateStatus } from '../api'

const CHECK_INTERVAL = 15 * 60 * 1000

export function useUpdateStatus() {
  const status = ref<UpdateStatus | null>(null)
  const healthVersion = ref('')
  const loading = ref(false)
  const error = ref('')
  const checkedAt = ref<Date | null>(null)
  let lastAttempt = 0
  let timer: ReturnType<typeof setInterval> | undefined

  async function refresh(force = true) {
    if (loading.value || !navigator.onLine || (!force && Date.now() - lastAttempt < CHECK_INTERVAL))
      return
    lastAttempt = Date.now()
    loading.value = true
    error.value = ''
    try {
      status.value = await api.updateStatus()
      checkedAt.value = new Date()
    } catch (failure) {
      error.value = failure instanceof Error ? failure.message : 'Update-Prüfung nicht erreichbar'
    } finally {
      loading.value = false
    }
  }

  function checkVisible() {
    if (!document.hidden) void refresh(false)
  }

  function checkOnline() {
    if (!document.hidden) void refresh()
  }

  onMounted(() => {
    void api
      .health()
      .then((health) => {
        healthVersion.value = health.version
      })
      .catch(() => {})
    checkVisible()
    timer = setInterval(checkVisible, CHECK_INTERVAL)
    document.addEventListener('visibilitychange', checkVisible)
    window.addEventListener('online', checkOnline)
  })

  onBeforeUnmount(() => {
    clearInterval(timer)
    document.removeEventListener('visibilitychange', checkVisible)
    window.removeEventListener('online', checkOnline)
  })

  return {
    status,
    version: computed(() => status.value?.version || healthVersion.value),
    loading,
    error,
    checkedAt,
    refresh,
  }
}
