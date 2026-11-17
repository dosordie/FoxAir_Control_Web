import { createApp, defineComponent } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../../src/api'
import { useAdminSession } from '../../src/composables/useAdminSession'

vi.mock('../../src/api', () => ({ api: { adminLogin: vi.fn(), adminLogout: vi.fn(), adminSession: vi.fn() } }))
let cleanup: (() => void) | undefined
function mount() {
  const onLogin = vi.fn().mockResolvedValue(undefined)
  const onLogout = vi.fn()
  let state!: ReturnType<typeof useAdminSession>
  const app = createApp(defineComponent({ setup() { state = useAdminSession(onLogin, onLogout); return () => null } }))
  app.mount(document.createElement('div'))
  cleanup = () => app.unmount()
  return { state, onLogin, onLogout }
}
afterEach(() => cleanup?.())

it('clears the password after login and fetches private settings only for an authenticated session', async () => {
  vi.mocked(api.adminLogin).mockResolvedValue({ authenticated: true, role: 'admin' })
  const { state, onLogin } = mount()
  state.cloudAdminPassword.value = 'test-password'
  await state.loginAsAdmin()
  expect(state.adminAuthenticated.value).toBe(true)
  expect(state.cloudAdminPassword.value).toBe('')
  expect(onLogin).toHaveBeenCalledOnce()
})

it('clears private client data even if the logout request fails', async () => {
  vi.mocked(api.adminLogout).mockRejectedValue(new Error('offline'))
  const { state, onLogout } = mount()
  state.adminAuthenticated.value = true
  state.cloudAdminPassword.value = 'test-password'
  await state.logoutAsAdmin()
  expect(state.adminAuthenticated.value).toBe(false)
  expect(state.cloudAdminPassword.value).toBe('')
  expect(onLogout).toHaveBeenCalledOnce()
})
