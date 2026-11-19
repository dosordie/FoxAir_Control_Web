import { createApp, defineComponent, h, nextTick, reactive } from 'vue'
import { describe, it, expect } from 'vitest'
import { heatpumpState } from '../src/telemetry'
import MainRegisterBrowser from '../src/components/MainRegisterBrowser.vue'
import type { RegisterValue, TransportId } from '../src/api'

const stamp = '2026-11-19T20:00:00Z'
const now = Date.parse(stamp)
const row = (register: number, value: number): RegisterValue => ({register, raw:value, value, unit:'', quality:'observed', transport:'display_modbus', timestamp:stamp})
describe('home operating symbols', () => {
  it('keeps selected cooling and actual defrost enums separate', () => {
    const cooling = heatpumpState(row(1012, 2), row(2012, 0), null, now)
    expect(cooling.cooling).toBe(true)
    expect(cooling.defrost).toBe(false)
    const defrost = heatpumpState(row(1012, 3), row(2012, 2), null, now)
    expect(defrost.defrost).toBe(true)
    expect(defrost.label).toBe('Heizen + Warmwasser')
    expect(defrost.water).toBe(true)
  })
  it('hides defrost on a later ordinary run value or an old measurement', () => {
    expect(heatpumpState(null,row(2012,1),null,now).defrost).toBe(false)
    expect(heatpumpState(null,row(2012,2),null,now+300001).defrost).toBe(false)
    expect(heatpumpState(row(1012,4),row(2012,0),null,now).label).toBe('Kühlen + Warmwasser')
    expect(heatpumpState(row(1012,1),row(2012,1),{...row(1011,0),value:'Aus'},now).label).toBe('')
  })
})
it('sorts every received register numerically and tracks only changed values within the same source', async () => {
  const props = reactive({transport:'display_modbus' as TransportId, rows:[row(2091,10), row(1001,0), row(2014,350)]})
  const root = document.createElement('div'); document.body.append(root)
  const app = createApp(defineComponent({setup:()=>()=>h(MainRegisterBrowser,props)})); app.mount(root)
  try {
    (root.querySelector('.register-preview-toggle') as HTMLButtonElement).click(); await nextTick()
    const rows = () => Array.from(root.querySelectorAll('tbody tr'))
    expect(rows().map(tr=>tr.firstElementChild?.textContent)).toEqual(['1001','2014','2091'])
    expect(rows()[0]!.classList.contains('area-settings')).toBe(true)
    expect(rows()[1]!.classList.contains('area-status')).toBe(true)
    const initial = rows()[0]
    props.rows = [row(2091,10), {...row(1001,0),timestamp:'2026-11-19T20:00:01Z'}, row(2014,350)]
    await nextTick()
    expect(rows()[0]).toBe(initial)
    expect(rows()[0]!.querySelector('.previous-register-value')?.textContent).toBe('—')
    props.rows = [row(2091,10), {...row(1001,1),timestamp:'2026-11-19T20:00:02Z'}, row(2014,350)]
    await nextTick()
    expect(rows()[0]!.querySelector('.previous-register-value')?.textContent).toBe('0')
    expect(rows()[0]!.classList.contains('register-changed')).toBe(true)
    props.transport = 'warmlink_raw'
    await nextTick()
    expect(rows()[0]!.querySelector('.previous-register-value')?.textContent).toBe('—')
    const filter=(name:string)=>Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.trim()===name)!
    filter('Livewerte').click();await nextTick();expect(rows()).toHaveLength(1)
    filter('Livewerte').click();await nextTick();expect(rows()).toHaveLength(3)
    filter('Einstellwerte').click();await nextTick();expect(rows()).toHaveLength(2)
    filter('Einstellwerte').click();await nextTick()
    const input = root.querySelector('input')!
    input.value = '2014';input.dispatchEvent(new Event('input'));await nextTick()
    expect(rows()).toHaveLength(1)
    expect(rows()[0]!.firstElementChild?.textContent).toBe('2014')
  } finally { app.unmount();root.remove() }
})
