import { createApp, defineComponent, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, type Dashboard, type LteSnapshot, type TransportId } from '../../src/api'
import { useLteConnection } from '../../src/composables/useLteConnection'

vi.mock('../../src/api', () => ({ api: { busLease: vi.fn(), busConnection: vi.fn(), lteScan: vi.fn(), lteSnapshot: vi.fn(), displaySnapshot:vi.fn(),displayScan:vi.fn(),displayLease:vi.fn() } }))

class Stream {
  static instances: Stream[] = []
  onmessage?: (event: { data: string }) => void
  onerror?: () => void
  close = vi.fn()
  constructor() { Stream.instances.push(this) }
  receive(packet: LteSnapshot) { this.onmessage?.({ data: JSON.stringify(packet) }) }
}
const packet = (): LteSnapshot => ({ values: {}, metrics: {}, connection: { connected: true, mode: 'browser', error: null, last_rx: null, lease_seconds: 80 }, scan: { status: 'idle', completed: 0, total: 8, error: null } })
const flush = async () => { await nextTick(); await Promise.resolve(); await Promise.resolve() }
let cleanup: (() => void) | undefined

function mount() {
  const transport = ref<TransportId>('warmlink_raw')
  const dashboard = ref<Dashboard | null>({ transport: 'warmlink_raw', metrics: { supply: null }, status: 'unavailable', timestamp: '', error: null } as Dashboard)
  const invalidate = vi.fn()
  let state!: ReturnType<typeof useLteConnection>
  const app = createApp(defineComponent({ setup() { state = useLteConnection(transport, dashboard, invalidate); return () => null } }))
  const target = document.createElement('div')
  app.mount(target)
  cleanup = () => { app.unmount(); target.remove() }
  return { state, transport, dashboard, invalidate }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('EventSource', Stream)
  Stream.instances = []
  vi.mocked(api.busLease).mockResolvedValue({})
  vi.mocked(api.lteSnapshot).mockResolvedValue(packet())
})
afterEach(() => { cleanup?.(); cleanup = undefined; vi.useRealTimers(); vi.unstubAllGlobals() })

describe('LTE connection ownership', () => {
  it('keeps newer measurements and clears old values on an empty reconnect snapshot', async () => {
    const { state, dashboard, invalidate } = mount()
    await flush()
    const stream = Stream.instances[0]!
    const row = { register: 2046, raw: 381, value: 38.1, unit: '°C', quality: 'observed', timestamp: new Date().toISOString(), transport: 'warmlink_raw' }
    stream.receive({ ...packet(), values: { '2046': row }, metrics: { supply: row } })
    stream.receive({ ...packet(), values: { '2046': { ...row, value: 1, timestamp: new Date(Date.now() - 60000).toISOString() } } })
    expect(state.localValues.value['2046']?.value).toBe(38.1)
    stream.receive({ ...packet(), reset: true })
    expect(state.localValues.value).toEqual({})
    expect(dashboard.value?.metrics.supply).toBeNull()
    expect(invalidate).toHaveBeenCalled()
  })

  it('rejects a delayed scan result and old stream messages after changing transport', async () => {
    const { state, transport } = mount()
    await flush()
    let finish!: (result: LteSnapshot['scan']) => void
    vi.mocked(api.lteScan).mockReturnValue(new Promise(resolve => { finish = resolve }))
    const oldStream = Stream.instances[0]!
    const pending = state.startLteScan()
    transport.value = 'cloud'
    await nextTick()
    transport.value = 'warmlink_raw'
    await nextTick()
    finish({ status: 'complete', completed: 8, total: 8, error: null })
    await pending
    oldStream.receive({ ...packet(), scan: { status: 'complete', completed: 8, total: 8, error: null } })
    expect(state.lteScan.value.status).toBe('idle')
    expect(oldStream.close).toHaveBeenCalledOnce()
    expect(state.scanStarting.value).toBe(false)
  })

  it('closes its stream and stops browser heartbeats when unmounted', async () => {
    const { state } = mount()
    await flush()
    const stream = Stream.instances[0]!
    const renewals = vi.mocked(api.busLease).mock.calls.length
    cleanup?.(); cleanup = undefined
    stream.receive({ ...packet(), scan: { status: 'complete', completed: 8, total: 8, error: null } })
    await vi.advanceTimersByTimeAsync(45000)
    expect(stream.close).toHaveBeenCalledOnce()
    expect(api.busLease).toHaveBeenCalledTimes(renewals)
    expect(state.lteScan.value.status).toBe('idle')
  })
})


it('display selection receives values passively and synchronizes only on explicit request',async()=>{
 vi.mocked(api.displaySnapshot).mockResolvedValue({...packet(),scan:{status:'idle',completed:0,total:6,error:null}})
 vi.mocked(api.displayLease).mockResolvedValue({})
 vi.mocked(api.displayScan).mockResolvedValue({status:'running',completed:0,total:6,error:null})
 const {state,transport}=mount();await flush()
 transport.value='display_modbus';await nextTick();await flush()
 const stream=Stream.instances[Stream.instances.length-1]!
 expect(api.displayScan).not.toHaveBeenCalled()
 const row={register:2046,raw:310,value:31,unit:'°C',quality:'observed',timestamp:new Date().toISOString(),transport:'display_modbus'}
 stream.receive({...packet(),values:{'2046':row}})
 expect(state.localValues.value['2046']?.transport).toBe('display_modbus')
 await state.startLteScan()
 expect(api.displayScan).toHaveBeenCalledOnce()
 transport.value='cloud';await nextTick()
 expect(stream.close).toHaveBeenCalledOnce()
})
