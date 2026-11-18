import { createApp, defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import ParameterFilters from '../src/components/ParameterFilters.vue'
import LteScanSummary from '../src/components/LteScanSummary.vue'
import ParameterValue from '../src/components/ParameterValue.vue'
import ParameterDetails from '../src/components/ParameterDetails.vue'

let cleanup: (()=>void)|undefined
afterEach(()=>{cleanup?.();cleanup=undefined;vi.unstubAllGlobals()})
function mount(component:Parameters<typeof createApp>[0],props?:Record<string,unknown>){
  const root=document.createElement('div');document.body.append(root)
  const app=createApp(component,props);app.mount(root)
  cleanup=()=>{app.unmount();root.remove()}
  return root
}

it('opens and focuses search, keeps a collapsed filter, and can clear it',async()=>{
  const search=ref('')
  const root=mount(defineComponent({setup:()=>()=>h(ParameterFilters,{
    search:search.value,group:'H',groups:[{group:'H',count:25}],showGroups:true,favoritesOnly:false,favoriteCount:2,
    'onUpdate:search':(text:string)=>{search.value=text},
  })}))
  const toggle=root.querySelector<HTMLButtonElement>('.mobile-search-toggle')!
  const input=root.querySelector<HTMLInputElement>('input')!
  expect(toggle.getAttribute('aria-expanded')).toBe('false')
  toggle.click();await nextTick();await nextTick()
  expect(toggle.getAttribute('aria-expanded')).toBe('true')
  expect(document.activeElement).toBe(input)
  input.value='H31';input.dispatchEvent(new Event('input',{bubbles:true}));await nextTick()
  input.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await nextTick()
  expect(toggle.getAttribute('aria-expanded')).toBe('false')
  expect(search.value).toBe('H31')
  expect(document.activeElement).toBe(toggle)
  toggle.click();await nextTick()
  root.querySelector<HTMLButtonElement>('.clear-search')!.click();await nextTick()
  expect(search.value).toBe('')
})

it('keeps the icon-only favorite button labelled and reports group selection',async()=>{
  const favorite=vi.fn(),select=vi.fn()
  const root=mount(ParameterFilters,{search:'',group:'',groups:[{group:'H',count:25}],showGroups:true,favoritesOnly:true,favoriteCount:2,onToggleFavorites:favorite,'onUpdate:group':select})
  const star=root.querySelector<HTMLButtonElement>('.favorite-filter')!
  expect(star.getAttribute('aria-label')).toBe('Alle Parameter anzeigen')
  expect(star.getAttribute('aria-pressed')).toBe('true')
  star.click();expect(favorite).toHaveBeenCalledOnce()
  root.querySelector<HTMLButtonElement>('.group-chip')!.click()
  expect(select).toHaveBeenCalledWith('H')
})

it('keeps the LTE summary compact while retaining errors and progress',()=>{
  const root=mount(LteScanSummary,{scan:{status:'running',completed:3,total:8,error:'Bus belegt'},valueCount:180,connected:true,starting:false})
  expect(root.querySelector('strong')?.textContent).toBe('LTE · 3/8 Blöcke')
  expect(root.querySelector('progress')?.getAttribute('value')).toBe('3')
  expect(root.querySelector('button')?.disabled).toBe(true)
  expect(root.querySelector('[role="alert"]')?.textContent).toBe('Bus belegt')
  expect(root.querySelector('.lte-summary-info')!.textContent!.length).toBeLessThan(60)
})

it('shows the complete long state in the wrapping text style',()=>{
  const value='Grundfos 25 – Zirkulationswasserpumpe mit integriertem Treiber'
  const root=mount(ParameterValue,{value,timestamp:'2026-11-18T12:00:00Z',quality:'stale'})
  expect(root.querySelector('.text-value strong')?.textContent?.trim()).toBe(value)
  expect(root.textContent).toContain('veraltet')
})


it('opens mobile details explicitly and can reopen the same parameter after closing',async()=>{
  const media=Object.assign(new EventTarget(),{matches:true})
  vi.stubGlobal('matchMedia',()=>media)
  let details:any
  const root=mount(defineComponent({setup:()=>()=>h(ParameterDetails,{ref:(value:any)=>{details=value}},()=>h('p','H20 details'))}))
  const dialog=root.querySelector('dialog')!
  expect(dialog.open).toBe(false)
  await details.open()
  expect(dialog.open).toBe(true)
  root.querySelector<HTMLButtonElement>('button')!.click()
  expect(dialog.open).toBe(false)
  await details.open()
  expect(dialog.open).toBe(true)
  expect(dialog.textContent).toContain('H20 details')
  media.matches=false;media.dispatchEvent(new Event('change'));await nextTick()
  expect(root.querySelector('dialog')).toBeNull()
  expect(root.querySelector('section')?.textContent).toBe('H20 details')
})
