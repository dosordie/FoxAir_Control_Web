import { computed, ref, watch, type Ref } from 'vue'
import { api } from '../api'

export function useLastDefrost(visible: Ref<boolean>) {
  const finish = ref<number | null>(null)
  const now = ref(Date.now())
  watch(
    visible,
    (shown, _, cleanup) => {
      if (!shown) return
      let active = true
      let nextRead: ReturnType<typeof setTimeout> | undefined
      async function refresh() {
        try {
          const result = await api.latestDefrost()
          if (active) {
            const time = result.finished_at ? Date.parse(result.finished_at) : NaN
            finish.value = Number.isFinite(time) ? time : null
          }
        } catch {
          // Keep an already known archive entry when the server is offline.
        }
        if (active) nextRead = setTimeout(refresh, 60000)
      }
      now.value = Date.now()
      void refresh()
      const clock = setInterval(() => {
        now.value = Date.now()
      }, 1000)
      cleanup(() => {
        active = false
        clearInterval(clock)
        clearTimeout(nextRead)
      })
    },
    { immediate: true },
  )
  return computed(() => {
    if (finish.value === null) return '—'
    const elapsed = Math.max(0, Math.floor((now.value - finish.value) / 60000))
    const hours = String(Math.floor(elapsed / 60)).padStart(2, '0')
    const minutes = String(elapsed % 60).padStart(2, '0')
    return `vor ${hours}:${minutes} h`
  })
}
