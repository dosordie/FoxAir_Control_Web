import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { api } from '../api'
import type { CloudConfigStatus, CloudDevice, TransportId, WarmlinkConfig } from '../api'

/** Own private settings, including protection against responses after logout. */
export function useConnectionSettings(
  authenticated: Readonly<Ref<boolean>>,
  secure: Readonly<Ref<boolean>>,
  onSaved: (transport: TransportId) => void,
  refreshCloud: () => void,
) {
  const cloudStatus = ref<CloudConfigStatus | null>(null)
  const cloudDevices = ref<CloudDevice[]>([])
  const cloudUsername = ref(''),
    cloudPassword = ref(''),
    cloudDeviceCode = ref('')
  const accountLoading = ref(false),
    accountLoaded = ref(false)
  const cloudSaving = ref(false),
    cloudDiscovering = ref(false),
    cloudScanLoading = ref(false)
  const cloudStatusLoading = ref(false),
    cloudMessage = ref(''),
    cloudError = ref('')
  const selectedCloudStatus = ref<Record<string, string | number | boolean | null>>({})
  const lteConfig = ref<WarmlinkConfig>({
    medium: 'tcp',
    serial_device: '',
    baudrate: 9600,
    host: '',
    port: 2001,
    enabled: false,
    slave: 99,
    connection_mode: 'on_demand',
    idle_timeout_seconds: 0,
    browser_timeout_seconds: 90,
  })
  const lteBusy = ref(false),
    lteMessage = ref(''),
    lteError = ref('')
  let epoch = 0
  let disposed = false

  function clearPrivateFields() {
    cloudUsername.value = ''
    cloudPassword.value = ''
    cloudDeviceCode.value = ''
    cloudDevices.value = []
    selectedCloudStatus.value = {}
    accountLoaded.value = false
    lteConfig.value = {
      medium: 'tcp',
      serial_device: '',
      baudrate: 9600,
      host: '',
      port: 2001,
      enabled: false,
      slave: 99,
      connection_mode: 'on_demand',
      idle_timeout_seconds: 0,
      browser_timeout_seconds: 90,
    }
    cloudMessage.value = ''
    cloudError.value = ''
    lteMessage.value = ''
    lteError.value = ''
    for (const busy of [
      accountLoading,
      cloudSaving,
      cloudDiscovering,
      cloudScanLoading,
      cloudStatusLoading,
      lteBusy,
    ])
      busy.value = false
  }
  async function adminAction(
    busy: Ref<boolean>,
    error: Ref<string>,
    fallback: string,
    action: (current: () => boolean) => Promise<void>,
  ) {
    if (!authenticated.value || !secure.value || disposed) return
    const requestEpoch = epoch
    const current = () => !disposed && requestEpoch === epoch && authenticated.value && secure.value
    busy.value = true
    error.value = ''
    try {
      await action(current)
    } catch (failure) {
      if (current()) error.value = failure instanceof Error ? failure.message : fallback
    } finally {
      if (current()) busy.value = false
    }
  }
  async function loadCloudStatus() {
    try {
      const result = await api.cloudStatus()
      if (!disposed) cloudStatus.value = result
    } catch {
      if (!disposed) cloudStatus.value = null
    }
  }
  function loadStoredAccount() {
    return adminAction(
      accountLoading,
      cloudError,
      'Kontodaten konnten nicht geladen werden.',
      async (current) => {
        const result = await api.cloudAccount('')
        if (!current()) return
        cloudUsername.value = result.username
        cloudDeviceCode.value = result.device_code
        accountLoaded.value = true
        cloudMessage.value = 'Aktuelle Cloud-E-Mail und Gerätekennung geladen.'
      },
    )
  }
  function loadLteConfig() {
    return adminAction(lteBusy, lteError, 'LTE-Einstellungen nicht verfügbar', async (current) => {
      const result = await api.warmlinkConfig()
      if (current())
        lteConfig.value = { medium: 'tcp', serial_device: '', baudrate: 9600, ...result }
    })
  }
  function saveLteConfig() {
    return adminAction(lteBusy, lteError, 'Speichern fehlgeschlagen', async (current) => {
      lteMessage.value = ''
      const result = await api.saveWarmlinkConfig(lteConfig.value)
      if (!current()) return
      lteConfig.value = result
      onSaved('warmlink_raw')
      lteMessage.value =
        'LTE-Anschluss gespeichert. Die Verbindung kann jetzt ausgewählt und geprüft werden.'
    })
  }
  function saveCloudSettings() {
    return adminAction(
      cloudSaving,
      cloudError,
      'Einstellungen konnten nicht gespeichert werden.',
      async (current) => {
        cloudMessage.value = ''
        const result = await api.cloudSave(
          '',
          cloudUsername.value,
          cloudPassword.value,
          cloudDeviceCode.value,
        )
        if (!current()) return
        cloudStatus.value = result
        cloudPassword.value = ''
        onSaved('cloud')
        cloudMessage.value =
          'Cloud-Einstellungen gespeichert. Verbindungsdaten werden nur auf dem Server abgelegt.'
      },
    )
  }
  function discoverCloudDevices() {
    return adminAction(
      cloudDiscovering,
      cloudError,
      'Geräteabfrage fehlgeschlagen',
      async (current) => {
        cloudMessage.value = ''
        const result = await api.cloudDevices('')
        if (!current()) return
        cloudDevices.value = result.items
        cloudMessage.value = result.count
          ? result.count + ' Cloud-Geräte gefunden.'
          : 'Keine Geräte gefunden.'
      },
    )
  }
  function queryCloudDeviceStatus() {
    return adminAction(
      cloudStatusLoading,
      cloudError,
      'Gerätestatus nicht verfügbar',
      async (current) => {
        const result = await api.cloudDeviceStatus('')
        if (current()) selectedCloudStatus.value = result.status
      },
    )
  }
  function rescanCloud() {
    return adminAction(
      cloudScanLoading,
      cloudError,
      'Scan konnte nicht gestartet werden',
      async (current) => {
        const result = await api.cloudScan('')
        if (!current()) return
        cloudMessage.value = result.started
          ? 'Cloud-Vollscan gestartet.'
          : 'Cloud-Vollscan läuft bereits.'
        refreshCloud()
      },
    )
  }
  onMounted(loadCloudStatus)
  watch(
    authenticated,
    (loggedIn) => {
      epoch += 1
      if (loggedIn) void Promise.all([loadStoredAccount(), loadLteConfig()])
      else clearPrivateFields()
    },
    { immediate: true },
  )
  onBeforeUnmount(() => {
    disposed = true
    epoch += 1
    clearPrivateFields()
  })
  return {
    cloudStatus,
    cloudDevices,
    cloudUsername,
    cloudPassword,
    cloudDeviceCode,
    accountLoading,
    accountLoaded,
    cloudSaving,
    cloudDiscovering,
    cloudScanLoading,
    cloudStatusLoading,
    cloudMessage,
    cloudError,
    selectedCloudStatus,
    lteConfig,
    lteBusy,
    lteMessage,
    lteError,
    loadStoredAccount,
    saveLteConfig,
    saveCloudSettings,
    discoverCloudDevices,
    queryCloudDeviceStatus,
    rescanCloud,
  }
}
