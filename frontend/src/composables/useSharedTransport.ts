import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, type TransportId } from '../api'

/** Only an explicit user choice sends a mutation; polling never writes it back. */
export function useSharedTransport() {
  const confirmed = ref<TransportId>('cloud')
  const busy = ref(true)
  const error = ref('')
  let revision = 0
  let disposed = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let initial: Promise<void> | undefined
  function apply(row: { transport: TransportId; revision: number }) {
    if (!disposed && row.revision >= revision) {
      revision = row.revision
      confirmed.value = row.transport
    }
  }
  async function refresh() {
    try {
      apply(await api.activeTransport())
    } catch {
      /* retain the last confirmed source */
    }
  }
  function initialize() {
    return (initial ||= refresh().finally(() => {
      if (!disposed) busy.value = false
    }))
  }
  async function choose(value: TransportId) {
    if (busy.value || value === confirmed.value) return
    busy.value = true
    error.value = ''
    try {
      apply(await api.selectTransport(value))
    } catch (failure) {
      if (!disposed)
        error.value = failure instanceof Error ? failure.message : 'Verbindung nicht geändert'
    } finally {
      if (!disposed) busy.value = false
    }
  }
  async function poll() {
    await refresh()
    if (!disposed) timer = setTimeout(poll, 2000)
  }
  const onVisibility = () => {
    if (!document.hidden) void refresh()
  }
  onMounted(() => {
    document.addEventListener('visibilitychange', onVisibility)
    void initialize().then(() => {
      if (!disposed) timer = setTimeout(poll, 2000)
    })
  })
  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onVisibility)
    disposed = true
    clearTimeout(timer)
  })
  return {
    selectedTransport: computed({
      get: () => confirmed.value,
      set: (value) => {
        void choose(value)
      },
    }),
    transportBusy: busy,
    transportError: error,
    initializeTransport: initialize,
  }
}
