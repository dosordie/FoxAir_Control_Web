import { onBeforeUnmount, ref } from 'vue'
import { api } from '../api'

export function useAdminSession(
  onLogin: () => Promise<unknown> = async () => {},
  onLogout: () => void = () => {},
) {
  const secureAdminContext =
    window.location.protocol === 'https:' ||
    ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)
  const signedIn = ref(false)
  const username = ref('admin')
  const role = ref('reader')
  const canOperate = ref(false)
  const adminAuthenticated = ref(false)
  const adminBusy = ref(false)
  const ssoAvailable = ref(false)
  const loginOpen = ref(false)
  const cloudAdminPassword = ref('')
  const adminLoginError = ref('')
  let disposed = false

  async function checkAdminSession() {
    try {
      const result = await api.adminSession()
      if (!disposed) {
        if (result.username) username.value = result.username
        signedIn.value = result.authenticated
        role.value = result.role
        canOperate.value = result.authenticated && result.role !== 'reader'
        adminAuthenticated.value = result.authenticated && result.role === 'admin'
        ssoAvailable.value = result.sso_available === true
      }
    } catch {
      if (!disposed) adminAuthenticated.value = false
    }
  }

  async function loginAsAdmin() {
    if (!secureAdminContext || !cloudAdminPassword.value || adminBusy.value) return
    adminBusy.value = true
    adminLoginError.value = ''
    try {
      const result = await api.adminLogin(cloudAdminPassword.value, username.value)
      if (disposed) return
      if (result.username) username.value = result.username
      signedIn.value = result.authenticated
      role.value = result.role
      canOperate.value = result.authenticated && result.role !== 'reader'
      adminAuthenticated.value = result.authenticated && result.role === 'admin'
      cloudAdminPassword.value = ''
      loginOpen.value = false
      if (result.authenticated) await onLogin()
    } catch (error) {
      if (disposed) return
      adminAuthenticated.value = false
      adminLoginError.value = error instanceof Error ? error.message : 'Anmeldung fehlgeschlagen'
    } finally {
      if (!disposed) adminBusy.value = false
    }
  }

  async function loginWithSso() {
    if (!secureAdminContext || adminBusy.value || !ssoAvailable.value) return
    adminBusy.value = true
    adminLoginError.value = ''
    try {
      const result = await api.adminSsoLogin()
      if (disposed) return
      if (result.username) username.value = result.username
      signedIn.value = result.authenticated
      role.value = result.role
      canOperate.value = result.authenticated && result.role !== 'reader'
      adminAuthenticated.value = result.authenticated && result.role === 'admin'
      cloudAdminPassword.value = ''
      loginOpen.value = false
      if (result.authenticated) await onLogin()
    } catch (error) {
      if (!disposed)
        adminLoginError.value =
          error instanceof Error ? error.message : 'SSO-Anmeldung fehlgeschlagen'
    } finally {
      if (!disposed) adminBusy.value = false
    }
  }

  async function logoutAsAdmin() {
    try {
      await api.adminLogout()
    } catch {
      /* Clear local sensitive fields even if the server is unreachable. */
    }
    adminAuthenticated.value = false
    signedIn.value = false
    role.value = 'reader'
    canOperate.value = false
    cloudAdminPassword.value = ''
    onLogout()
  }

  onBeforeUnmount(() => {
    disposed = true
    cloudAdminPassword.value = ''
  })
  return {
    secureAdminContext,
    signedIn,
    username,
    role,
    canOperate,
    ssoAvailable,
    loginWithSso,
    adminAuthenticated,
    adminBusy,
    loginOpen,
    cloudAdminPassword,
    adminLoginError,
    checkAdminSession,
    loginAsAdmin,
    logoutAsAdmin,
  }
}
