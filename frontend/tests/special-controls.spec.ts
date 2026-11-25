import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type RegisterValue } from '../src/api'
import SpecialControls from '../src/components/SpecialControls.vue'
import HeatingCurve from '../src/components/HeatingCurve.vue'

vi.mock('../src/api',()=>({api:{registers:vi.fn(),writeParameter:vi.fn()}}))
let cleanup: (()=>void)|undefined
afterEach(()=>{cleanup?.();cleanup=undefined;vi.unstubAllGlobals()})

it('uses all seven firmware curve points, including 1235 at zero degrees, with distinct editor labels',async()=>{
  const points=[[-20,1250],[-10,1251],[-5,1252],[0,1235],[5,1253],[10,1254],[20,1255]]
  const values:Record<number,RegisterValue>={}
  const row=(register:number,value:number)=>({register,value,raw:value*10,transport:'warmlink_raw',timestamp:new Date().toISOString(),quality:'fresh',unit:'°C'})
  points.forEach((point,index)=>{values[point[1]]=row(point[1],50-index*5)})
  values[1236]={...row(1236,2),raw:2};values[1164]=row(1164,20);values[1165]=row(1165,60)
  vi.mocked(api.registers).mockResolvedValue({catalog_size:7,items:points.map(point=>({register:point[1],name:'Kurvenpunkt',code:'',group:'OTHER',description:'',unit:'°C',type:'TEMP1',mode:'r/w',write_available:true,value_map:{}}))})
  const root=document.createElement('div')
  const app=createApp(SpecialControls,{dialog:{id:'at',title:'AT-Kurve',description:'',codes:[],count:7,read_only:false,registers:points.map(p=>p[1]),curve_points:points.map(p=>({outdoor:p[0],register:p[1]}))},transport:'warmlink_raw',admin:true,valueFor:(register:number)=>values[register]||null})
  app.mount(root);cleanup=()=>app.unmount()
  await Promise.resolve();await nextTick()
  expect(root.querySelectorAll('circle')).toHaveLength(7)
  expect(root.textContent).toContain('0 °C außen: 35 °C Sollwert')
  const ids=Array.from(root.querySelectorAll('input')).map(input=>input.id)
  expect(ids).toHaveLength(7)
  expect(new Set(ids).size).toBe(7)

  const point = root.querySelector<SVGCircleElement>('circle[aria-label="0 °C außen, Sollwert 35 °C"]')!
  point.setPointerCapture = vi.fn()
  const svg = root.querySelector('svg[viewBox="0 0 520 250"]') as SVGSVGElement
  svg.getScreenCTM = () => new DOMMatrix()
  vi.stubGlobal('DOMPoint', class {
    constructor(_x: number, public y: number) {}
    matrixTransform() { return this }
  })
  const pointer = { pointerType: 'mouse', isPrimary: true, pointerId: 1 }
  point.dispatchEvent(new PointerEvent('pointerdown', { ...pointer, clientY: 133 }))
  point.dispatchEvent(new PointerEvent('pointermove', { ...pointer, clientY: 111 }))
  point.dispatchEvent(new PointerEvent('pointerup', { ...pointer, clientY: 111 }))
  await nextTick()
  const draft = root.querySelector<HTMLInputElement>('.curve-panel input')!
  expect(draft.value).toBe('40')
  expect(api.writeParameter).not.toHaveBeenCalled()
  vi.mocked(api.writeParameter).mockResolvedValue({ confirmed: true, status: 'confirmed' })
  root.querySelector<HTMLButtonElement>('.curve-panel .main-action')!.click()
  expect(api.writeParameter).toHaveBeenCalledWith(1235, 'warmlink_raw', '40', '350', 'warmlink_raw')
  await nextTick()

})

it('draws the standard curve with plateaus exactly where the limits are crossed', () => {
  const values: Record<number, number> = { 1236: 1, 1234: 1, 1235: 35, 1164: 20, 1165: 50 }
  const root = document.createElement('div')
  const app = createApp(HeatingCurve, {
    points: [], registers: [], transport: 'display_modbus', admin: true,
    valueFor: (register: number) => values[register] == null ? null : {
      register, value: values[register], raw: null, transport: 'display_modbus', timestamp: '',
      quality: 'observed', unit: '',
    },
  })
  app.mount(root)
  cleanup = () => app.unmount()

  expect(root.querySelector('polyline')?.getAttribute('points')).toBe(
    '62,24 115.75,24 438.25,198 492,198',
  )
  expect(root.querySelectorAll('circle')).toHaveLength(0)
})
