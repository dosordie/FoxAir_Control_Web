import { createApp, defineComponent, nextTick, ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type Register, type TransportId } from '../../src/api'
import { useRegisterCatalog } from '../../src/composables/useRegisterCatalog'
import type { Page } from '../../src/types/navigation'

vi.mock('../../src/api', () => ({ api: { registers: vi.fn(), registerGroups: vi.fn() } }))
let cleanup: (() => void) | undefined
function mount() {
  let state!: ReturnType<typeof useRegisterCatalog>
  const app = createApp(defineComponent({ setup() { state = useRegisterCatalog(ref<TransportId>('warmlink_raw'), ref<Page>('home'), vi.fn()); return () => null } }))
  app.mount(document.createElement('div'))
  cleanup = () => app.unmount()
  return state
}
const row: Register = { register:1105,code:'D01',group:'D',name:'Example',description:'',unit:'°C',type:'TEMP1',mode:'r/w',write_available:false,value_map:{} }
beforeEach(() => { vi.useFakeTimers(); vi.mocked(api.registerGroups).mockResolvedValue({items:[]}) })
afterEach(() => { cleanup?.(); cleanup=undefined; vi.useRealTimers() })

it('does not let an older search response overwrite the latest catalog result', async () => {
  let finish!: (value:{items:Register[];catalog_size:number})=>void
  vi.mocked(api.registers).mockReturnValueOnce(new Promise(resolve=>{finish=resolve})).mockResolvedValueOnce({items:[row],catalog_size:896})
  const state=mount()
  const older=state.loadRegisters()
  state.search.value='D01'
  await nextTick()
  await state.loadRegisters()
  finish({items:[{...row,code:'OLD'}],catalog_size:1})
  await older
  expect(state.registers.value.map(item=>item.code)).toEqual(['D01'])
  expect(state.catalogSize.value).toBe(896)
})

it('discards responses after the catalog owner has been removed', async () => {
  let finish!: (value:{items:Register[];catalog_size:number})=>void
  vi.mocked(api.registers).mockReturnValueOnce(new Promise(resolve=>{finish=resolve}))
  const state=mount(),pending=state.loadRegisters()
  cleanup?.();cleanup=undefined
  finish({items:[row],catalog_size:896})
  await pending
  expect(state.registers.value).toEqual([])
})
