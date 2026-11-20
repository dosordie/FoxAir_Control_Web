import {createApp,defineComponent,h,nextTick,reactive} from 'vue'
import {it,expect,vi,afterEach} from 'vitest'
import AppHeader from '../src/components/AppHeader.vue'
import SetupWizard from '../src/components/SetupWizard.vue'
let cleanup:(()=>void)|undefined
afterEach(()=>{cleanup?.();vi.unstubAllGlobals()})
const flush=async()=>{await Promise.resolve();await Promise.resolve();await nextTick();await nextTick()}
it('closes the account popover on outside pointer and Escape and clears password',async()=>{
 const state=reactive({page:'home' as const,authenticated:true,busy:false,secure:true,error:'',loginOpen:true,password:'private-draft'})
 const root=document.createElement('div');document.body.append(root)
 const app=createApp(defineComponent({setup:()=>()=>h(AppHeader,{...state,'onUpdate:loginOpen':(v:boolean)=>state.loginOpen=v,'onUpdate:password':(v:string)=>state.password=v})}));app.mount(root)
 cleanup=()=>{app.unmount();root.remove()}
 document.body.dispatchEvent(new Event('pointerdown',{bubbles:true}));await nextTick()
 expect(root.querySelector('.login-popover')).toBeNull();expect(state.password).toBe('')
 state.loginOpen=true;await nextTick();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));await nextTick()
 expect(root.querySelector('.login-popover')).toBeNull()
})
it('requires matching new passwords and completes the one-time setup without silently logging in',async()=>{
 const fetch=vi.fn(async(url:string)=>({ok:true,json:async()=>url.endsWith('/status')?{required:true,container:true}:{configured:true}}))
 vi.stubGlobal('fetch',fetch)
 const completed=vi.fn(),root=document.createElement('div');document.body.append(root)
 const app=createApp(SetupWizard,{onCompleted:completed});app.mount(root);cleanup=()=>{app.unmount();root.remove()}
 await flush()
 const inputs=Array.from(root.querySelectorAll('input'))
 for(const [index,value] of ['test-local-code','new-test-password','different-password'].entries()){inputs[index]!.value=value;inputs[index]!.dispatchEvent(new Event('input'))}
 root.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await nextTick()
 expect(fetch).toHaveBeenCalledTimes(1)
 expect(root.textContent).toContain('stimmen nicht')
 inputs[2]!.value='new-test-password';inputs[2]!.dispatchEvent(new Event('input'))
 root.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flush()
 expect(completed).toHaveBeenCalledOnce();expect(root.querySelector('dialog')).toBeNull()
 expect(fetch).toHaveBeenCalledTimes(2)
})
