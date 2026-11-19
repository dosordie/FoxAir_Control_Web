import {createApp,defineComponent,h,nextTick,reactive} from 'vue'
import {it,expect,vi,afterEach} from 'vitest'
import LocalBusSettings from '../src/components/LocalBusSettings.vue'
let cleanup:(()=>void)|undefined
afterEach(()=>{cleanup?.();vi.unstubAllGlobals()})
it('does not expose a delayed bus configuration after losing admin access',async()=>{
 let complete!:(value:unknown)=>void
 vi.stubGlobal('fetch',vi.fn(()=>new Promise(resolve=>{complete=resolve})))
 const state=reactive({admin:true,secure:true,open:true})
 const root=document.createElement('div');document.body.append(root)
 const app=createApp(defineComponent({setup:()=>()=>h(LocalBusSettings,state)}));app.mount(root)
 cleanup=()=>{app.unmount();root.remove()}
 state.admin=false;await nextTick()
 complete({ok:true,json:async()=>({host:'192.168.1.50',port:2001,slave:3,timeout:2,enabled:true,connection_mode:'browser',browser_timeout_seconds:90})})
 await Promise.resolve();await Promise.resolve();await nextTick()
 expect(Array.from(root.querySelectorAll<HTMLInputElement>('input[placeholder]')).every(input=>input.value==='')).toBe(true)
 expect(root.querySelector('fieldset')?.disabled).toBe(true)
})
