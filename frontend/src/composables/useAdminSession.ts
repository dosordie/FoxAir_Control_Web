import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from '../api'

export function useAdminSession(
  onLogin: () => Promise<unknown> = async () => {},
  onLogout: () => void = () => {},
) {
  const lanHttp = ref(false)
  const secureAdminContext = computed(
    () =>
      lanHttp.value ||
      window.location.protocol === 'https:' ||
      ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname),
  )
  const signedIn = ref(false)
  const sessionChecked = ref(false)
  const username = ref('admin')
  const sessionUsername = ref('')
  const role = ref('reader')
  const canOperate = ref(false)
  const adminAuthenticated = ref(false)
  const adminBusy = ref(false)
  const ssoAvailable = ref(false)
  const loginOpen = ref(false)
  const cloudAdminPassword = ref('')
  const adminLoginError = ref('')
  let disposed = false

  function clearAuthorization() {
    adminAuthenticated.value = false
    signedIn.value = false
    sessionUsername.value = ''
    role.value = 'reader'
    canOperate.value = false
  }

  async function checkAdminSession() {
    try {
      const result = await api.adminSession()
      if (!disposed) {
        if (result.username) username.value = result.username
        sessionUsername.value = result.authenticated ? (result.username ?? '') : ''
        signedIn.value = result.authenticated
        role.value = result.role
        canOperate.value = result.authenticated && result.role !== 'reader'
        adminAuthenticated.value = result.authenticated && result.role === 'admin'
        ssoAvailable.value = result.sso_available === true
        lanHttp.value = result.lan_http === true
      }
    } catch {
      if (!disposed) clearAuthorization()
    } finally {
      if (!disposed) sessionChecked.value = true
    }
  }

  async function loginAsAdmin() {
    if (!secureAdminContext.value || !cloudAdminPassword.value || adminBusy.value) return
    adminBusy.value = true
    adminLoginError.value = ''
    try {
      const result = await api.adminLogin(cloudAdminPassword.value, username.value)
      if (disposed) return
      if (result.username) username.value = result.username
      sessionUsername.value = result.authenticated ? (result.username ?? '') : ''
      signedIn.value = result.authenticated
      role.value = result.role
      canOperate.value = result.authenticated && result.role !== 'reader'
      adminAuthenticated.value = result.authenticated && result.role === 'admin'
      cloudAdminPassword.value = ''
      loginOpen.value = false
      if (result.authenticated) await onLogin()
    } catch (error) {
      if (disposed) return
      clearAuthorization()
      adminLoginError.value = error instanceof Error ? error.message : 'Anmeldung fehlgeschlagen'
    } finally {
      if (!disposed) adminBusy.value = false
    }
  }

  async function loginWithSso() {
    if (!secureAdminContext.value || adminBusy.value || !ssoAvailable.value) return
    adminBusy.value = true
    adminLoginError.value = ''
    try {
      const result = await api.adminSsoLogin()
      if (disposed) return
      if (result.username) username.value = result.username
      sessionUsername.value = result.authenticated ? (result.username ?? '') : ''
      signedIn.value = result.authenticated
      role.value = result.role
      canOperate.value = result.authenticated && result.role !== 'reader'
      adminAuthenticated.value = result.authenticated && result.role === 'admin'
      cloudAdminPassword.value = ''
      loginOpen.value = false
      if (result.authenticated) await onLogin()
    } catch (error) {
      if (!disposed) {
        clearAuthorization()
        adminLoginError.value =
          error instanceof Error ? error.message : 'SSO-Anmeldung fehlgeschlagen'
      }
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
    sessionUsername.value = ''
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
    sessionChecked,
    secureAdminContext,
    signedIn,
    username,
    sessionUsername,
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
