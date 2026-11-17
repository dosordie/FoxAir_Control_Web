import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type RegisterValue } from '../src/api'
import SpecialControls from '../src/components/SpecialControls.vue'

vi.mock('../src/api',()=>({api:{registers:vi.fn()}}))
let cleanup: (()=>void)|undefined
afterEach(()=>{cleanup?.();cleanup=undefined})

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
})
