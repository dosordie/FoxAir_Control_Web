import { createApp, defineComponent, nextTick, ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '../../src/api'
import { useConnectionSettings } from '../../src/composables/useConnectionSettings'

vi.mock('../../src/api', () => ({ api: {
  cloudStatus: vi.fn(), cloudAccount: vi.fn(), warmlinkConfig: vi.fn(), cloudSave: vi.fn(),
  cloudDevices: vi.fn(), cloudScan: vi.fn(), cloudDeviceStatus: vi.fn(), saveWarmlinkConfig: vi.fn(),
} }))
let cleanup: (() => void) | undefined
function mount(loggedIn = true, secureContext = true) {
  const authenticated = ref(loggedIn), secure = ref(secureContext)
  const saved = vi.fn(), refresh = vi.fn()
  let state!: ReturnType<typeof useConnectionSettings>
  const app = createApp(defineComponent({ setup() { state = useConnectionSettings(authenticated, secure, saved, refresh); return () => null } }))
  app.mount(document.createElement('div'))
  cleanup = () => app.unmount()
  return { state, authenticated, saved }
}
beforeEach(() => {
  vi.mocked(api.cloudStatus).mockResolvedValue({ configured: true, username_configured: true, password_configured: true, device_configured: true, admin_enabled: true, storage: 'private' })
  vi.mocked(api.warmlinkConfig).mockResolvedValue({ host: '192.168.1.5', port: 2001, slave: 99, enabled: true, connection_mode: 'on_demand' })
  vi.mocked(api.cloudAccount).mockResolvedValue({ username: 'example-user', device_code: 'example-device' })
})
afterEach(() => cleanup?.())

it('cannot restore private fields when an account response arrives after logout', async () => {
  let finish!: (result: {username:string;device_code:string}) => void
  vi.mocked(api.cloudAccount).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const { state, authenticated } = mount()
  authenticated.value = false
  await nextTick()
  finish({ username: 'old-private-user', device_code: 'old-private-device' })
  await Promise.resolve(); await nextTick()
  expect(state.cloudUsername.value).toBe('')
  expect(state.cloudDeviceCode.value).toBe('')
  expect(state.accountLoaded.value).toBe(false)
  expect(state.lteConfig.value.enabled).toBe(false)
})

it.each([[false, true], [true, false]])('does not send settings without admin and secure context (%s, %s)', async (admin, secure) => {
  const { state, saved } = mount(admin, secure)
  state.cloudPassword.value = 'example-secret'
  await state.saveCloudSettings()
  expect(api.cloudSave).not.toHaveBeenCalled()
  expect(saved).not.toHaveBeenCalled()
})
