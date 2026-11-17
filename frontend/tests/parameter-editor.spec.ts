import { createApp, defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type Register, type RegisterValue } from '../src/api'
import ParameterEditor from '../src/components/ParameterEditor.vue'
import CompressorGauge from '../src/components/CompressorGauge.vue'
import { fanIsRunning } from '../src/telemetry'

vi.mock('../src/api', () => ({ api: { read: vi.fn(), writeParameter: vi.fn() } }))
const entry: Register = {register:1105,code:'D01',group:'D',name:'Abtauen',description:'',unit:'°C',type:'TEMP1',mode:'r/w',write_available:true,value_map:{}}
const value = (): RegisterValue => ({register:1105,raw:125,value:12.5,unit:'°C',transport:'warmlink_raw',timestamp:new Date().toISOString(),quality:'cached'})
let cleanup: (()=>void) | undefined
const flush = async () => { await nextTick(); await Promise.resolve(); await nextTick() }
function mountEditor(row = ref<RegisterValue|null>(value())) {
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp(defineComponent({setup:()=>()=>h(ParameterEditor,{register:entry,transport:'warmlink_raw',admin:true,value:row.value})}))
  app.mount(root)
  cleanup = () => {app.unmount();root.remove()}
  return {root,row}
}
beforeEach(()=>{ vi.clearAllMocks();vi.mocked(api.writeParameter).mockResolvedValue({status:'unchanged',confirmed:true,code:'D01'}) })
afterEach(()=>{cleanup?.();cleanup=undefined})

it('can submit an existing valid value without a separate read click', async()=>{
  const {root}=mountEditor()
  const button=Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.includes('mit Readback'))!
  expect(button.disabled).toBe(false)
  button.click();await flush()
  expect(api.read).not.toHaveBeenCalled()
  expect(api.writeParameter).toHaveBeenCalledWith(1105,'warmlink_raw','12.5','125','warmlink_raw')
})

it('passes the original Cloud baseline to the server when editing via LTE', async()=>{
  const {root}=mountEditor(ref({...value(),raw:null,value:'12.5',transport:'cloud'}))
  Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.includes('mit Readback'))!.click()
  await flush()
  expect(api.read).not.toHaveBeenCalled()
  expect(api.writeParameter).toHaveBeenCalledWith(1105,'warmlink_raw','12.5','12.5','cloud')
})

it('does not overwrite an edited draft or its conflict baseline on live updates', async()=>{
  const {root,row}=mountEditor()
  const input=root.querySelector('input')!
  input.value='15';input.dispatchEvent(new Event('input',{bubbles:true}))
  await nextTick()
  row.value={...value(),raw:130,value:13};await nextTick()
  expect(input.value).toBe('15')
  Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.includes('mit Readback'))!.click()
  await flush()
  expect(api.writeParameter).toHaveBeenCalledWith(1105,'warmlink_raw','15','125','warmlink_raw')
})

it('does not offer a write baseline for missing data', ()=>{
  const {root}=mountEditor(ref(null))
  expect(root.querySelector('input')).toBeNull()
  expect(root.textContent).not.toContain('Wert mit Readback senden')
})

it('shows the minimum running frequency as about 31 percent without a percent caption', ()=>{
  const root=document.createElement('div')
  const app=createApp(CompressorGauge,{metric:{...value(),value:28}})
  app.mount(root);cleanup=()=>app.unmount()
  expect(root.textContent?.trim()).toBe('28 Hz')
  const fill=root.querySelector<HTMLElement>('.compressor-fill')!
  expect(parseFloat(fill.style.width)).toBeCloseTo(31.11,1)
  expect(root.textContent).not.toContain('%')
})

it('keeps the fan running with usable telemetry even if other metrics are missing', ()=>{
  const power={...value(),value:'1'}
  expect(fanIsRunning(power,null,[])).toBe(true)
  expect(fanIsRunning({...power,quality:'stale'},{...power,value:28},[])).toBe(true)
  expect(fanIsRunning(power,{...power,value:28},[{...power,value:0}])).toBe(false)
  expect(fanIsRunning({...power,quality:'stale'},null,[])).toBe(false)
})
