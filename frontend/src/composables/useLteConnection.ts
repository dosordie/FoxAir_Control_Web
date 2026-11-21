import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { api } from '../api'
import type {
  ConnectionState,
  Dashboard,
  LteScan,
  LteSnapshot,
  RegisterValue,
  TransportId,
} from '../api'

const emptyScan = (): LteScan => ({ status: 'idle', completed: 0, total: 8, error: null })

/** Own the browser stream, lease timer and local register cache in one scope. */
export function useLteConnection(
  transport: Ref<TransportId>,
  dashboard: Ref<Dashboard | null>,
  invalidateReadValues: () => void,
) {
  const busState = ref<ConnectionState | null>(null)
  const localValues = ref<Record<string, RegisterValue>>({})
  const lteScan = ref<LteScan>(emptyScan())
  const pushConnected = ref(false)
  const scanStarting = ref(false)
  let events: EventSource | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let started = false
  let disposed = false
  let generation = 0

  function applySnapshot(incoming: LteSnapshot) {
    if (disposed || !['warmlink_raw', 'display_modbus'].includes(transport.value)) return
    busState.value = incoming.connection
    const resetValues =
      incoming.removed?.length || (incoming.reset && !Object.keys(incoming.values).length)
    if (resetValues) {
      invalidateReadValues()
      if (dashboard.value?.transport === transport.value) {
        for (const key of Object.keys(dashboard.value.metrics) as (keyof Dashboard['metrics'])[]) {
          dashboard.value.metrics[key] = null
        }
      }
    }
    if (incoming.reset) localValues.value = {}
    for (const key of incoming.removed || []) delete localValues.value[key]
    for (const [key, next] of Object.entries(incoming.values)) {
      const previous = localValues.value[key]
      if (!previous || Date.parse(next.timestamp) >= Date.parse(previous.timestamp))
        localValues.value[key] = next
    }
    lteScan.value = incoming.scan

    const current = dashboard.value
    if (current?.transport !== transport.value) return
    for (const key of Object.keys(incoming.metrics) as (keyof Dashboard['metrics'])[]) {
      const next = incoming.metrics[key]
      const previous = current.metrics[key]
      if (
        next &&
        (!previous ||
          (key === 'target' && next.source_code === '2014' && previous.source_code !== '2014') ||
          Date.parse(next.timestamp) >= Date.parse(previous.timestamp))
      )
        current.metrics[key] = next
      const shown = current.metrics[key]
      if (
        shown &&
        ((!incoming.connection.connected && shown.quality === 'observed') ||
          Date.now() - Date.parse(shown.timestamp) > 300000)
      )
        shown.quality = 'stale'
    }
    const fresh = Object.values(current.metrics).filter(
      (item) => item && ['fresh', 'observed'].includes(item.quality),
    ).length
    current.status =
      fresh === Object.keys(current.metrics).length ? 'online' : fresh ? 'partial' : 'unavailable'
    current.error = incoming.connection.error
  }

  function connectStream() {
    events?.close()
    events = undefined
    pushConnected.value = false
    if (disposed || !['warmlink_raw', 'display_modbus'].includes(transport.value)) return
    const stream = new EventSource(
      transport.value === 'display_modbus'
        ? '/api/local/display_modbus/events'
        : '/api/warmlink/events',
    )
    events = stream
    stream.onmessage = (event) => {
      if (events !== stream || disposed) return
      try {
        applySnapshot(JSON.parse(event.data) as LteSnapshot)
        pushConnected.value = true
      } catch {
        pushConnected.value = false
      }
    }
    stream.onerror = () => {
      if (events === stream) pushConnected.value = false
    }
  }

  async function refreshSnapshot() {
    const requestedGeneration = generation
    const incoming =
      transport.value === 'display_modbus' ? await api.displaySnapshot() : await api.lteSnapshot()
    if (!disposed && requestedGeneration === generation) applySnapshot({ ...incoming, reset: true })
  }

  async function renewLease() {
    if (disposed) return
    const requestedGeneration = generation
    try {
      if (['warmlink_raw', 'display_modbus'].includes(transport.value)) {
        if (transport.value === 'display_modbus') await api.displayLease()
        else await api.busLease()
        if (!pushConnected.value) await refreshSnapshot()
      } else if (transport.value === 'standard_modbus') {
        await api.standardLease()
      } else {
        const state = await api.busConnection()
        if (!disposed && requestedGeneration === generation) busState.value = state
      }
    } catch {
      // SSE reconnects automatically. Keep the original confirmed timestamps.
    } finally {
      if (!disposed) timer = setTimeout(renewLease, 15000)
    }
  }

  async function startLteScan() {
    if (
      scanStarting.value ||
      lteScan.value.status === 'running' ||
      !['warmlink_raw', 'display_modbus'].includes(transport.value)
    )
      return
    const requestedGeneration = generation
    scanStarting.value = true
    try {
      const result =
        transport.value === 'display_modbus' ? await api.displayScan() : await api.lteScan()
      if (disposed || requestedGeneration !== generation) return
      lteScan.value = result
      await refreshSnapshot()
    } catch (error) {
      if (!disposed && requestedGeneration === generation)
        lteScan.value = {
          ...lteScan.value,
          status: 'error',
          error: error instanceof Error ? error.message : 'Busabfrage fehlgeschlagen',
        }
    } finally {
      if (requestedGeneration === generation) scanStarting.value = false
    }
  }

  watch(transport, () => {
    generation += 1
    localValues.value = {}
    busState.value = null
    lteScan.value = { ...emptyScan(), total: transport.value === 'display_modbus' ? 6 : 8 }
    scanStarting.value = false
    if (started) connectStream()
  })
  onMounted(() => {
    started = true
    connectStream()
    void renewLease()
  })
  onBeforeUnmount(() => {
    disposed = true
    generation += 1
    events?.close()
    events = undefined
    clearTimeout(timer)
  })

  return {
    busState,
    localValues,
    lteScan,
    pushConnected,
    scanStarting,
    startLteScan,
    refreshSnapshot,
  }
}
