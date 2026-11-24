import { computed, ref, watch, type Ref } from 'vue'
import { api, type TimerM1, type TransportId } from '../api'
import { inM1Window } from '../timerWindow'
import type { Page } from '../types/navigation'

export function useTimerSummary(
  page: Ref<Page>,
  selectedTransport: Ref<TransportId>,
  transportPaused: Ref<boolean>,
  selected: Ref<boolean>,
) {
  const m1Limit = ref<TimerM1 | null>(null)
  const m1Clock = ref(new Date())
  const m1Status = computed(() =>
    m1Limit.value?.enabled == null
      ? 'Status unbekannt'
      : m1Limit.value.enabled
        ? 'Aktiviert'
        : 'Deaktiviert',
  )
  const m1InWindow = computed(() => inM1Window(m1Limit.value, m1Clock.value))
  watch(
    [page, selectedTransport, transportPaused, selected],
    ([current, transport, paused, visible], _, cleanup) => {
      m1Limit.value = null
      if (current !== 'home' || paused || !visible) return
      let active = true
      let timer: ReturnType<typeof setTimeout> | undefined
      cleanup(() => {
        active = false
        clearTimeout(timer)
      })
      async function refresh() {
        m1Clock.value = new Date()
        if (!document.hidden && navigator.onLine) {
          try {
            const value = await api.timerM1(transport)
            if (active) m1Limit.value = value
          } catch {
            if (active && m1Limit.value) m1Limit.value = { ...m1Limit.value, stale: true }
          }
        }
        if (active) timer = setTimeout(refresh, 30000)
      }
      void refresh()
    },
    { immediate: true },
  )
  return { m1Limit, m1Status, m1InWindow }
}
