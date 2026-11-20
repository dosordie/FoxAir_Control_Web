import {createApp,defineComponent,h,nextTick,reactive} from 'vue'
import {afterEach,it,expect,vi} from 'vitest'
import ExpertGira from '../src/components/ExpertGira.vue'
let cleanup:(()=>void)|undefined
afterEach(()=>{cleanup?.();vi.unstubAllGlobals();vi.useRealTimers()})
const flush=async()=>{await Promise.resolve();await Promise.resolve();await nextTick();await nextTick()}
it('renders numeric zero and text safely using only the read endpoint',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({enabled:true,connected:true,error:null,items:[{id:0,name:'PV',value:0,unit:'kW',quality:'observed',timestamp:null},{id:1,name:'Text',value:'<img src=x>',unit:'',quality:'observed',timestamp:null}]})})))
 const root=document.createElement('div');document.body.append(root);const app=createApp(ExpertGira);app.mount(root);cleanup=()=>{app.unmount();root.remove()}
 await flush()
 expect(root.textContent).toContain('0')
 expect(root.textContent).toContain('<img src=x>')
 expect(root.querySelector('img')).toBeNull()
 expect(vi.mocked(fetch).mock.calls.every(([url])=>url==='/api/expert/gira/state')).toBe(true)
})
it('does not restore private connection fields from a late response after losing admin access',async()=>{
 let complete!:(value:unknown)=>void
 vi.stubGlobal('fetch',vi.fn((url:string)=>url.endsWith('/config')?new Promise(resolve=>{complete=resolve}):Promise.resolve({ok:true,json:async()=>({enabled:false,connected:false,error:null,items:[]})})))
 const state=reactive({settings:true,admin:true,secure:true})
 const root=document.createElement('div');document.body.append(root);const app=createApp(defineComponent({setup:()=>()=>h(ExpertGira,state)}));app.mount(root);cleanup=()=>{app.unmount();root.remove()}
 const details=root.querySelector('details')!;details.open=true;details.dispatchEvent(new Event('toggle'));await nextTick()
 state.admin=false;await nextTick()
 complete({ok:true,json:async()=>({enabled:true,host:'192.168.1.50',username:'private',password:'',objects:[]})})
 await flush()
 expect(root.querySelector('fieldset')?.disabled).toBe(true)
 expect(Array.from(root.querySelectorAll('input')).some(input=>input.value==='192.168.1.50')).toBe(false)
})
