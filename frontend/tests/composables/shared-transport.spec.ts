import { createApp, defineComponent, nextTick } from 'vue'
import { afterEach, it, expect, vi } from 'vitest'
import { api, type TransportId } from '../../src/api'
import { useSharedTransport } from '../../src/composables/useSharedTransport'
vi.mock('../../src/api',()=>({api:{activeTransport:vi.fn(),selectTransport:vi.fn()}}))
let cleanup:(()=>void)[]=[]
afterEach(()=>{cleanup.forEach(fn=>fn());cleanup=[];vi.useRealTimers();vi.clearAllMocks()})
function mount(){
 let state!:ReturnType<typeof useSharedTransport>
 const app=createApp(defineComponent({setup(){state=useSharedTransport();return()=>null}}));const root=document.createElement('div');app.mount(root)
 cleanup.push(()=>app.unmount());return state
}
it('synchronizes two browsers and never echoes a remote selection back as a mutation',async()=>{
 vi.useFakeTimers()
 let server={transport:'display_modbus' as TransportId,revision:1}
 vi.mocked(api.activeTransport).mockImplementation(async()=>({...server}))
 vi.mocked(api.selectTransport).mockImplementation(async transport=>({...server={transport,revision:server.revision+1}}))
 const a=mount(),b=mount();await Promise.all([a.initializeTransport(),b.initializeTransport()])
 expect(a.selectedTransport.value).toBe('display_modbus')
 a.selectedTransport.value='cloud';await nextTick();await Promise.resolve()
 await vi.advanceTimersByTimeAsync(2000)
 expect(b.selectedTransport.value).toBe('cloud')
 expect(api.selectTransport).toHaveBeenCalledTimes(1)
})
it('keeps the confirmed source when a change is denied',async()=>{
 vi.mocked(api.activeTransport).mockResolvedValue({transport:'display_modbus',revision:1})
 vi.mocked(api.selectTransport).mockRejectedValue(new Error('Admin-Anmeldung erforderlich'))
 const state=mount();await state.initializeTransport();state.selectedTransport.value='cloud';await nextTick();await Promise.resolve()
 expect(state.selectedTransport.value).toBe('display_modbus')
 expect(state.transportError.value).toContain('Admin')
})
