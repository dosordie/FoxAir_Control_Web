import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import UpdatePanel from '../src/components/UpdatePanel.vue'
let cleanup: (() => void) | undefined
afterEach(() => { cleanup?.(); vi.unstubAllGlobals() })
async function render(update: boolean) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({
    version: update ? '0.1.0' : '0.2.0', available_version: update ? '0.2.0' : '0.1.0',
    current: 'a'.repeat(40), deployed: 'a'.repeat(40), remote: 'b'.repeat(40),
    build_consistent: true, build_ready: true, update_available: update,
    update_mode: 'release', installed: true,
  }) })))
  const root = document.createElement('div'); document.body.append(root)
  const app = createApp(UpdatePanel, { admin: true, secure: true }); app.mount(root)
  cleanup = () => { app.unmount(); root.remove() }
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await nextTick(); await nextTick()
  return root
}
it('does not mistake an older latest release with another SHA for a new version', async () => {
  const root = await render(false)
  expect(root.textContent).toContain('Kein neueres freigegebenes Release verfügbar')
  expect(root.textContent).not.toContain('Neue Version verfügbar')
  expect([...root.querySelectorAll('button')].find(b => b.textContent?.includes('Jetzt über GitHub'))?.disabled).toBe(true)
})
it('offers a ready newer release based on the server version decision', async () => {
  const root = await render(true)
  expect(root.textContent).toContain('Freigegebenes Release 0.2.0 ist verfügbar')
  expect([...root.querySelectorAll('button')].find(b => b.textContent?.includes('Jetzt über GitHub'))?.disabled).toBe(false)
})
