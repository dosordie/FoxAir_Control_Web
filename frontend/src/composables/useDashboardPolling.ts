import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { api, type Dashboard, type TransportId } from '../api'
import type { Page } from '../types/navigation'

export function useDashboardPolling(
  selectedTransport: Ref<TransportId>,
  page: Ref<Page>,
  refreshLastValues: () => Promise<void>,
  refreshCloudValues: () => Promise<void>,
) {
  const snapshot = ref<Dashboard | null>(null)
  const refreshing = ref(false)
  const error = ref('')
  const liveEnabled = ref(window.localStorage.getItem('foxair.cloudLiveEnabled') !== 'false')
  const storedInterval = Number(window.localStorage.getItem('foxair.cloudLiveInterval') || 30)
  const liveInterval = ref(
    Number.isFinite(storedInterval) ? Math.max(10, Math.min(3600, storedInterval)) : 30,
  )
  const liveActive = computed(
    () =>
      page.value === 'home' &&
      !document.hidden &&
      (selectedTransport.value === 'standard_modbus' ||
        (selectedTransport.value === 'cloud' && liveEnabled.value)),
  )
  let refreshTimer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  function scheduleRefresh() {
    clearTimeout(refreshTimer)
    if (disposed || !liveActive.value) return
    const seconds = Number.isFinite(liveInterval.value)
      ? Math.max(10, Math.min(3600, liveInterval.value))
      : 30
    refreshTimer = setTimeout(() => {
      void loadDashboard(true)
    }, seconds * 1000)
  }

  let dashboardGeneration = 0
  let dashboardSource: TransportId | null = null
  async function loadDashboard(live = false) {
    if (disposed) return
    const source = selectedTransport.value
    if (refreshing.value && dashboardSource === source) return
    const generation = ++dashboardGeneration
    dashboardSource = source
    refreshing.value = true
    error.value = ''
    try {
      const data = await api.dashboard(source, live && source === 'cloud')
      if (generation !== dashboardGeneration || source !== selectedTransport.value) return
      snapshot.value = data
      void refreshLastValues()
      if (data.error) error.value = data.error
      if (source === 'cloud') void refreshCloudValues()
    } catch (err) {
      if (generation === dashboardGeneration && source === selectedTransport.value)
        error.value = err instanceof Error ? err.message : 'Keine Verbindung zum Webserver'
    } finally {
      if (generation === dashboardGeneration) {
        refreshing.value = false
        scheduleRefresh()
      }
    }
  }

  function stopRefresh() {
    clearTimeout(refreshTimer)
  }

  watch(selectedTransport, (transport) => {
    stopRefresh()
    if (snapshot.value) {
      const now = Date.now()
      const metrics = Object.fromEntries(
        Object.entries(snapshot.value.metrics).map(([key, metric]) => [
          key,
          metric
            ? {
                ...metric,
                quality: now - Date.parse(metric.timestamp) > 300000 ? 'stale' : 'cached',
              }
            : null,
        ]),
      ) as Dashboard['metrics']
      snapshot.value = { ...snapshot.value, transport, status: 'unavailable', error: null, metrics }
    }
    void loadDashboard()
  })

  watch([liveEnabled, liveInterval], () => {
    window.localStorage.setItem('foxair.cloudLiveEnabled', String(liveEnabled.value))
    window.localStorage.setItem('foxair.cloudLiveInterval', String(liveInterval.value))
    scheduleRefresh()
  })
  onBeforeUnmount(() => {
    disposed = true
    dashboardGeneration++
    stopRefresh()
  })

  return {
    snapshot,
    refreshing,
    error,
    liveEnabled,
    liveInterval,
    loadDashboard,
    scheduleRefresh,
    stopRefresh,
  }
}
