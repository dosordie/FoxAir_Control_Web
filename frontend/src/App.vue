<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Activity, ArrowDownLeft, ArrowLeft, ArrowRight, ArrowUpRight, Bell,
  ChevronRight, Clock3, Cloud, Fan, Gauge, HeartPulse, House,
  Minus, Plus, Power, RadioTower, RefreshCw, Search,
  Settings2, ShieldCheck, SlidersHorizontal, Star,
  Sun, Thermometer, VolumeX, Waves, Wifi, Zap
} from 'lucide-vue-next'
import { api } from './api'
import type { CloudConfigStatus, CloudDevice, CloudRow, CloudLog, CloudValues, Dashboard, Metric, Register, RegisterValue, SpecialDialog, Transport, TransportId, UpdateStatus } from './api'

type Page = 'home' | 'parameters' | 'settings'
const validIds: TransportId[] = ['cloud', 'standard_modbus', 'display_modbus', 'warmlink_raw']
const storedId = window.localStorage.getItem('foxair.lastTransport') as TransportId
const selectedTransport = ref<TransportId>(validIds.includes(storedId) ? storedId : 'cloud')
const transports = ref<Transport[]>([])
const page = ref<Page>('home')
const snapshot = ref<Dashboard | null>(null)
const refreshing = ref(false)
const error = ref('')
const search = ref('')
const selectedGroup = ref('')
const registerGroups = ref<{ group: string; count: number }[]>([])
const cloudStatus = ref<CloudConfigStatus | null>(null)
const cloudDevices = ref<CloudDevice[]>([])
const cloudRows = ref<CloudRow[]>([])
const cloudOverview = ref<CloudValues | null>(null)
const cloudLogs = ref<CloudLog[]>([])
const specialDialogs = ref<SpecialDialog[]>([])
const specialDialog = ref<string | null>(null)
const specialLoading = ref(false)
const specialError = ref('')
const specialMessage = ref('')
const selectedSpecial = computed(() => specialDialogs.value.find(x => x.id === specialDialog.value) || null)
const specialRows = computed(() => {
  const selected = selectedSpecial.value
  if (!selected) return []
  const byCode = new Map(cloudRows.value.map(row => [row.code, row]))
  return selected.codes.map(code => byCode.get(code)).filter((row): row is CloudRow => !!row)
})
const cloudView = ref(false)
const cloudKind = ref('')
const cloudCodeSelected = ref<CloudRow | null>(null)
const accountLoading = ref(false)
const accountLoaded = ref(false)
const cloudScanLoading = ref(false)
const updateInfo = ref<UpdateStatus | null>(null)
const updateLoading = ref(false)
const updateRequesting = ref(false)
const updateError = ref('')
const updateMessage = ref('')
let valuesTimer: ReturnType<typeof setTimeout> | undefined
const selectedCloudStatus = ref<Record<string, string | number | boolean | null>>({})
const cloudStatusLoading = ref(false)
const cloudUsername = ref('')
const cloudPassword = ref('')
const cloudDeviceCode = ref('')
const cloudAdminPassword = ref('')
const cloudSaving = ref(false)
const cloudDiscovering = ref(false)
const cloudMessage = ref('')
const cloudError = ref('')
const secureAdminContext = window.location.protocol === 'https:' ||
  ['127.0.0.1', 'localhost', '[::1]'].includes(window.location.hostname)
const liveEnabled = ref(window.localStorage.getItem('foxair.cloudLiveEnabled') !== 'false')
const storedInterval = Number(window.localStorage.getItem('foxair.cloudLiveInterval') || 30)
const liveInterval = ref(Number.isFinite(storedInterval) ? Math.max(10, Math.min(3600, storedInterval)) : 30)
const liveActive = computed(() => page.value === 'home' && selectedTransport.value === 'cloud' &&
  liveEnabled.value && !document.hidden)
let refreshTimer: ReturnType<typeof setTimeout> | undefined
let unmounted = false
const registers = ref<Register[]>([])
const catalogSize = ref(0)
const registerLoading = ref(false)
const selectedRegister = ref<Register | null>(null)
const reading = ref(false)
const currentValue = ref<RegisterValue | null>(null)
const readError = ref('')
let searchTimer: ReturnType<typeof setTimeout> | undefined

const selectedTransportInfo = computed(() => transports.value.find(t => t.id === selectedTransport.value))
const transportLabel = computed(() => selectedTransportInfo.value?.name || 'PHNIX-Cloud')
const online = computed(() => snapshot.value?.status === 'online')
const modeText = computed(() => displayMetric(snapshot.value?.metrics.mode || null, '—'))
const powerText = computed(() => displayMetric(snapshot.value?.metrics.power || null, '—'))
const fanRunning = computed(() =>
  snapshot.value?.status !== 'unavailable' &&
  snapshot.value?.metrics.power?.quality !== 'stale' &&
  ['Ein', '1', 'ON'].includes(powerText.value))
const mainRegisterOpen = ref(false)
const mainRegisterGroup = ref('T')
const mainRegisterSearch = ref('')
const mainRegisterRows = computed(() => {
  const query = mainRegisterSearch.value.trim().toLowerCase()
  return cloudRows.value.filter(row =>
    (!mainRegisterGroup.value || row.group === mainRegisterGroup.value) &&
    (!query || [row.name, row.code, String(row.register ?? '')]
      .some(text => text.toLowerCase().includes(query)))
  ).slice(0, 60)
})
const filteredCloudRows = computed(() => {
  const term = search.value.trim().toLowerCase()
  return cloudRows.value.filter(row => {
    if (cloudKind.value && row.kind !== cloudKind.value) return false
    return !term || [row.code, row.name, String(row.register ?? ''), row.group]
      .some(part => part.toLowerCase().includes(term))
  })
})

const cloudByRegister = computed(() => {
  const result = new Map<number, CloudRow>()
  for (const item of cloudRows.value) {
    if (item.register == null || item.value === null) continue
    const current = result.get(item.register)
    if (!current || (item.confidence === 'confirmed' && current.confidence !== 'confirmed')) {
      result.set(item.register, item)
    }
  }
  return result
})
function currentCloudRegisterValue(register: number) {
  return cloudByRegister.value.get(register) || null
}
function textValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}
function relativeTimestamp(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString('de-DE') : 'Noch kein aktueller Cloud-Wert'
}

const lastUpdated = computed(() => {
  if (!snapshot.value?.timestamp) return 'Noch keine Messwerte'
  if (snapshot.value.status === 'unavailable') {
    const last = Object.values(snapshot.value.metrics).find(v => v?.quality === 'stale')
    return last?.timestamp ? 'Verbindung unterbrochen · letzter Messwert ' +
      new Date(last.timestamp).toLocaleString('de-DE') : 'Verbindung unterbrochen'
  }
  return 'Abfrage ' + new Date(snapshot.value.timestamp).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})
const actionButtons = [
  { label: 'Timer', hint: 'Zeitprogramme', icon: Clock3, color: 'apricot', dialog: 'timer' },
  { label: 'SG-Ready', hint: 'PV-Steuerung', icon: Zap, color: 'mint', dialog: 'sg' },
  { label: 'AT-Kurve', hint: 'Heizkennlinie', icon: Sun, color: 'lilac', dialog: 'at' },
  { label: 'Wärmepumpe', hint: 'Sollwerte', icon: Thermometer, color: 'mint', dialog: 'wp' },
  { label: 'Ruhemodus', hint: 'Silent-Timer', icon: VolumeX, color: 'apricot', dialog: 'silent' },
  { label: 'Störungen', hint: 'Fehlerstatus', icon: Bell, color: 'lilac', dialog: 'fault' },
]
const readings = computed(() => [
  { key: 'flow', label: 'Durchfluss', icon: Waves, unit: 'm³/h' },
  { key: 'tank', label: 'Warmwasser', icon: Thermometer, unit: '°C' },
  { key: 'outdoor', label: 'Außen', icon: Sun, unit: '°C' },
  { key: 'return', label: 'Rücklauf', icon: ArrowDownLeft, unit: '°C' },
  { key: 'supply', label: 'Vorlauf', icon: ArrowUpRight, unit: '°C' },
] as const)

function displayMetric(metric: Metric, fallback = '—'): string {
  if (metric?.value === null || metric?.value === undefined) return fallback
  return typeof metric.value === 'number'
    ? metric.value.toLocaleString('de-DE', { maximumFractionDigits: 2 })
    : String(metric.value)
}
function metric(key: keyof Dashboard['metrics']) {
  return displayMetric(snapshot.value?.metrics[key] || null)
}
function routeFromHash(): Page {
  const path = window.location.hash.slice(1).split('?')[0]
  return path === '/parameters' ? 'parameters' : path === '/settings' ? 'settings' : 'home'
}
function syncRoute() {
  page.value = routeFromHash()
  scheduleRefresh()
  scheduleValueRefresh()
  if (page.value === 'settings') {
    void loadCloudLogs()
    void loadCloudStatus()
    void loadGitUpdateStatus()
  }
}
function navigate(target: Page, term = '') {
  if (target === 'parameters' && term) search.value = term
  window.location.hash = target === 'home' ? '#/' : '#/' + target
  syncRoute()
  if (target === 'parameters') {
    void loadRegisters()
    void loadCloudValues()
  }
}
function scheduleRefresh() {
  clearTimeout(refreshTimer)
  if (unmounted || !liveActive.value) return
  const seconds = Number.isFinite(liveInterval.value)
    ? Math.max(10, Math.min(3600, liveInterval.value)) : 30
  refreshTimer = setTimeout(() => { void loadDashboard(true) }, seconds * 1000)
}

async function loadDashboard(live = false) {
  if (refreshing.value) return
  const source = selectedTransport.value
  refreshing.value = true
  error.value = ''
  try {
    const data = await api.dashboard(source, live && source === 'cloud')
    if (source !== selectedTransport.value) return
    snapshot.value = data
    if (data.error) error.value = data.error
    if (source === 'cloud') void loadCloudValues()
  } catch (err) {
    if (source === selectedTransport.value)
      error.value = err instanceof Error ? err.message : 'Keine Verbindung zum Webserver'
  } finally {
    refreshing.value = false
    scheduleRefresh()
  }
}

function onVisibilityChange() {
  clearTimeout(refreshTimer)
  if (!document.hidden && page.value === 'home') {
    void loadDashboard(false)
  }
  if (!document.hidden && page.value === 'parameters') {
    void loadCloudValues()
    scheduleValueRefresh()
  }
}

function scheduleValueRefresh() {
  clearTimeout(valuesTimer)
  if (unmounted || page.value !== 'parameters' || document.hidden) return
  valuesTimer = setTimeout(async () => {
    await loadCloudValues()
    scheduleValueRefresh()
  }, cloudOverview.value?.status === 'running' ? 5000 : 15000)
}
async function loadCloudValues() {
  try {
    cloudOverview.value = await api.cloudValues()
    cloudRows.value = cloudOverview.value.items
    if (cloudCodeSelected.value) {
      cloudCodeSelected.value = cloudRows.value.find(row => row.code === cloudCodeSelected.value?.code) || null
    }
    // The register table can show current values directly from cloudRows.
  } catch {
    // Preserve the last known values until the next refresh.
  }
}
async function openSpecialDialog(dialog: string) {
  specialError.value = ''
  specialMessage.value = ''
  if (!specialDialogs.value.length) {
    try { specialDialogs.value = (await api.specialDialogs()).items }
    catch { specialError.value = 'Spezialdialoge derzeit nicht verfügbar'; return }
  }
  if (!specialDialogs.value.some(x => x.id === dialog)) return
  specialDialog.value = dialog
  await loadCloudValues()
  void refreshSelectedSpecial()
}
async function refreshSelectedSpecial() {
  const id = specialDialog.value
  if (!id || specialLoading.value) return
  specialLoading.value = true
  specialError.value = ''
  specialMessage.value = ''
  try {
    const result = await api.refreshSpecialDialog(id)
    specialMessage.value = result.updated
      ? result.count + ' aktuelle Cloudwerte gelesen'
      : result.reason === 'rate_limit'
        ? 'Bereits kürzlich abgefragt, bitte den Cache verwenden.'
        : 'Noch keine bestätigten Codes für diesen Dialog.'
    await loadCloudValues()
  } catch (e) {
    specialError.value = e instanceof Error ? e.message : 'Cloud-Abfrage fehlgeschlagen'
  } finally {
    specialLoading.value = false
  }
}
function closeSpecialOnEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') specialDialog.value = null
}

async function loadCloudLogs() {
  try { cloudLogs.value = (await api.cloudLogs()).items }
  catch { /* Logs are optional and must not block operation */ }
}
async function loadStoredAccount() {
  accountLoading.value = true
  cloudError.value = ''
  try {
    const result = await api.cloudAccount(cloudAdminPassword.value)
    cloudUsername.value = result.username
    cloudDeviceCode.value = result.device_code
    accountLoaded.value = true
    cloudMessage.value = 'Aktuelle Cloud-E-Mail und Gerätekennung geladen.'
  } catch (e) {
    cloudError.value = e instanceof Error ? e.message : 'Kontodaten konnten nicht geladen werden.'
  } finally {
    accountLoading.value = false
  }
}
async function rescanCloud() {
  cloudScanLoading.value = true
  cloudError.value = ''
  try {
    const result = await api.cloudScan(cloudAdminPassword.value)
    cloudMessage.value = result.started ? 'Cloud-Vollscan gestartet.' : 'Cloud-Vollscan läuft bereits.'
    await loadCloudValues()
  } catch (e) {
    cloudError.value = e instanceof Error ? e.message : 'Scan konnte nicht gestartet werden'
  } finally {
    cloudScanLoading.value = false
  }
}

async function loadGitUpdateStatus() {
  updateLoading.value = true
  updateError.value = ''
  try { updateInfo.value = await api.updateStatus() }
  catch (e) { updateError.value = e instanceof Error ? e.message : 'Update-Status nicht erreichbar' }
  finally { updateLoading.value = false }
}
async function submitGitUpdate() {
  if (!secureAdminContext || !cloudAdminPassword.value) {
    updateError.value = 'HTTPS und Web-Administrationspasswort erforderlich.'
    return
  }
  updateRequesting.value = true
  updateError.value = ''
  updateMessage.value = ''
  try {
    await api.requestUpdate(cloudAdminPassword.value)
    updateMessage.value = 'Update angefordert. Der getrennte FoxAir-Updater prüft und installiert den passenden Git-Build. Die Web-App kann dabei kurz neu starten.'
    // Do not claim an installation succeeded: completion is observed separately.
  } catch (e) {
    updateError.value = e instanceof Error ? e.message : 'Update-Anforderung fehlgeschlagen'
  } finally {
    updateRequesting.value = false
  }
}

async function loadCloudStatus() {
  try { cloudStatus.value = await api.cloudStatus() }
  catch { cloudStatus.value = null }
}

async function saveCloudSettings() {
  if (!secureAdminContext) {
    cloudError.value = 'Cloud-Konfiguration nur über HTTPS oder einen lokalen SSH-Tunnel.'
    return
  }
  cloudSaving.value = true
  cloudError.value = ''
  cloudMessage.value = ''
  try {
    cloudStatus.value = await api.cloudSave(
      cloudAdminPassword.value, cloudUsername.value, cloudPassword.value, cloudDeviceCode.value
    )
    cloudPassword.value = ''
    cloudMessage.value = 'Cloud-Einstellungen gespeichert. Verbindungsdaten werden nur auf dem Server abgelegt.'
    const list = await api.transports()
    transports.value = list.items
    if (selectedTransport.value === 'cloud') void loadDashboard()
  } catch (e) {
    cloudError.value = e instanceof Error ? e.message : 'Einstellungen konnten nicht gespeichert werden.'
  } finally {
    cloudSaving.value = false
  }
}

async function queryCloudDeviceStatus() {
  cloudStatusLoading.value = true
  cloudError.value = ''
  try {
    selectedCloudStatus.value = (await api.cloudDeviceStatus(cloudAdminPassword.value)).status
  } catch (e) {
    cloudError.value = e instanceof Error ? e.message : 'Gerätestatus nicht verfügbar'
  } finally {
    cloudStatusLoading.value = false
  }
}

async function discoverCloudDevices() {
  cloudDiscovering.value = true
  cloudError.value = ''
  cloudMessage.value = ''
  try {
    const result = await api.cloudDevices(cloudAdminPassword.value)
    cloudDevices.value = result.items
    cloudMessage.value = result.count ? result.count + ' Cloud-Geräte gefunden.' : 'Keine Geräte gefunden.'
  } catch (e) {
    cloudError.value = e instanceof Error ? e.message : 'Geräteabfrage fehlgeschlagen'
  } finally {
    cloudDiscovering.value = false
  }
}
async function loadRegisters() {
  registerLoading.value = true
  try {
    const result = await api.registers(search.value, selectedGroup.value)
    registers.value = result.items
    catalogSize.value = result.catalog_size
  } catch (err) {
    readError.value = err instanceof Error ? err.message : 'Registerkatalog nicht erreichbar'
    registers.value = []
  } finally {
    registerLoading.value = false
  }
}
function selectRegister(item: Register) {
  selectedRegister.value = item
  currentValue.value = null
  readError.value = ''
}
async function readRegister() {
  if (!selectedRegister.value) return
  reading.value = true
  readError.value = ''
  currentValue.value = null
  try {
    currentValue.value = await api.read(selectedRegister.value.register, selectedTransport.value)
  } catch (err) {
    readError.value = err instanceof Error ? err.message : 'Lesefehler'
  } finally {
    reading.value = false
  }
}
watch(selectedTransport, (value) => {
  window.localStorage.setItem('foxair.lastTransport', value)
  currentValue.value = null
  clearTimeout(refreshTimer)
  snapshot.value = null
  void loadDashboard()
})
watch([liveEnabled, liveInterval], () => {
  window.localStorage.setItem('foxair.cloudLiveEnabled', String(liveEnabled.value))
  window.localStorage.setItem('foxair.cloudLiveInterval', String(liveInterval.value))
  scheduleRefresh()
})
watch(selectedGroup, () => {
  selectedRegister.value = null
  if (page.value === 'parameters') void loadRegisters()
})
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { if (page.value === 'parameters') void loadRegisters() }, 240)
})
onMounted(async () => {
  syncRoute()
  window.addEventListener('hashchange', syncRoute)
  document.addEventListener('visibilitychange', onVisibilityChange)
  document.addEventListener('keydown', closeSpecialOnEscape)
  try {
    const response = await api.transports()
    transports.value = response.items
  } catch {
    // Backend not reachable; show unavailable values, never demo values.
  }
  await Promise.all([loadDashboard(), loadCloudStatus(), loadCloudValues()])
  try { specialDialogs.value = (await api.specialDialogs()).items } catch { specialDialogs.value = [] }
  try { registerGroups.value = (await api.registerGroups()).items } catch { registerGroups.value = [] }
  if (page.value === 'parameters') await loadRegisters()
  if (page.value === 'settings') await Promise.all([loadCloudLogs(), loadGitUpdateStatus()])
  scheduleRefresh()
  scheduleValueRefresh()
})
onBeforeUnmount(() => {
  unmounted = true
  window.removeEventListener('hashchange', syncRoute)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  document.removeEventListener('keydown', closeSpecialOnEscape)
  clearTimeout(searchTimer)
  clearTimeout(refreshTimer)
  clearTimeout(valuesTimer)
  cloudAdminPassword.value = ''
  cloudPassword.value = ''
})
</script>

<template>
  <div class="app-shell">
    <header class="shell-header">
      <button class="brand" type="button" @click="navigate('home')" aria-label="Zur Übersicht">
        <span class="brand-mark official-brand"><img src="/foxye-logo.png" alt="FoxAir-Logo" /></span>
        <span><strong>FoxAir</strong><small>CONTROL WEB</small></span>
      </button>
      <nav class="desktop-nav" aria-label="Hauptnavigation">
        <button :class="{ selected: page === 'home' }" @click="navigate('home')">Übersicht</button>
        <button :class="{ selected: page === 'parameters' }" @click="navigate('parameters')">Parameter</button>
        <button :class="{ selected: page === 'settings' }" @click="navigate('settings')">Einstellungen</button>
      </nav>
      <div class="shell-header-right">
        <span class="mini-label">FoxAir 9 Greenline</span>
        <button class="header-icon" type="button" @click="navigate('settings')" aria-label="App-Einstellungen"><Settings2 :size="21" /></button>
      </div>
    </header>

    <main>
      <template v-if="page === 'home'">
        <section class="heat-hero">
          <div class="room-illustration" aria-hidden="true"><i></i><i></i><i></i></div>
          <div class="hero-content">
            <div class="hero-top">
              <div class="device-name"><span class="device-kicker">DEINE WÄRMEPUMPE</span><h1>FoxAir 9 Greenline</h1></div>
              <div class="connection">
                <span class="connection-dot" :class="{ online }"></span>
                <span>{{ online ? 'Verbunden' : snapshot?.status === 'partial' ? 'Teilweise verbunden' : 'Nicht verbunden' }}</span>
              </div>
            </div>
            <div class="hero-main">
              <div class="unit-container" aria-label="Illustration einer Wärmepumpe">
                <div class="unit">
                  <div class="fan-ring" :class="{ 'fan-running': fanRunning }"><Fan :size="94" :stroke-width="1.3" /></div>
                  <span class="unit-brand">FOX<span>AIR</span></span>
                </div>
                <span class="unit-ground"></span>
              </div>
              <div class="target-temperature">
                <span class="overline">{{ snapshot?.metrics.target?.label || 'Heizungs-Basissollwert' }}</span>
                <div class="temp-adjust">
                  <button class="round-adjust" type="button" disabled title="Sollwertschreiben folgt in einer späteren Version" aria-label="Solltemperatur senken"><Minus :size="25" /></button>
                  <strong>{{ metric('target') }}<small v-if="snapshot?.metrics.target"> °C</small></strong>
                  <button class="round-adjust" type="button" disabled title="Sollwertschreiben folgt in einer späteren Version" aria-label="Solltemperatur erhöhen"><Plus :size="25" /></button>
                </div>
                <span class="hero-footnote">
                  {{ snapshot?.metrics.target?.source_code === '2014' ? 'Betriebsabhängig gewählter Wassersollwert (2014)' : 'Basiswert R02 · ohne bestätigte Korrektur' }}
                  <template v-if="snapshot?.metrics.base_target && snapshot?.metrics.target?.source_code === '2014'">
                    · R02: {{ displayMetric(snapshot.metrics.base_target) }} °C
                  </template>
                </span>
                <button class="refresh-inline" type="button" :disabled="refreshing" @click="loadDashboard(false)">
                  <RefreshCw :size="15" :class="{ spinning: refreshing }" /> {{ refreshing ? 'Lese Werte …' : 'Jetzt aktualisieren' }}
                </button>
              </div>
            </div>
            <div class="hero-metrics">
              <div v-for="item in readings" :key="item.key" class="hero-metric"
                :class="{ 'is-stale': snapshot?.metrics[item.key]?.quality === 'stale' }"
                :title="snapshot?.metrics[item.key]?.quality === 'stale' ? 'Letzter bekannter Wert, Verbindung unterbrochen' : ''">
                <component :is="item.icon" :size="24" :stroke-width="1.8" />
                <strong>{{ metric(item.key) }}</strong>
                <span class="metric-unit">{{ item.unit }}</span>
                <span class="metric-label">{{ item.label }}</span>
              </div>
            </div>
          </div>
        </section>

        <div class="below-hero">
          <div v-if="error" class="notice" role="status">
            <Bell :size="18" /><div><strong>Keine vollständigen Livewerte</strong><span>{{ error }}</span></div>
          </div>

          <section class="status-strip">
            <div class="status-main">
              <div class="status-symbol"><HeartPulse :size="22" /></div>
              <div><span class="section-caption">ANLAGENSTATUS</span>
                <h2 v-if="snapshot?.status === 'unavailable'">Offline · letzter Zustand: {{ powerText }}</h2>
                <h2 v-else>{{ powerText === '—' ? 'Status nicht verfügbar' : powerText === 'Ein' ? 'Anlage eingeschaltet' : powerText === 'Aus' ? 'Anlage ausgeschaltet' : 'Betrieb: ' + powerText }}</h2>
                <p>{{ lastUpdated }}</p></div>
            </div>
            <div class="transport-inline">
              <label for="home-transport">Verbindung</label>
              <select id="home-transport" v-model="selectedTransport">
                <option value="cloud">PHNIX-Cloud</option>
                <option value="standard_modbus">Standard-Modbus</option>
                <option value="display_modbus">Display-Modbus</option>
                <option value="warmlink_raw">LTE-/Warmlink-Modbus</option>
              </select>
              <div class="live-inline" v-if="selectedTransport === 'cloud'">
                <label class="live-switch"><input type="checkbox" v-model="liveEnabled" /> Automatische Cloud-Abfrage</label>
                <small>{{ liveEnabled ? 'alle ' + liveInterval + ' s · nur bei sichtbarer Übersicht' : 'deaktiviert' }}</small>
              </div>
            </div>
          </section>

          <div class="content-columns">
            <section class="shortcuts panel">
              <div class="section-head"><div><span class="section-caption">SCHNELLZUGRIFF</span><h2>Funktionen</h2></div><span class="muted-text">Parameter auswählen</span></div>
              <div class="shortcut-grid">
                <button v-for="button in actionButtons" :key="button.label" class="shortcut" @click="openSpecialDialog(button.dialog)">
                  <span class="shortcut-symbol" :class="button.color"><component :is="button.icon" :size="28" /></span>
                  <strong>{{ button.label }}</strong>
                  <small>{{ button.hint }}</small>
                  <ChevronRight :size="16" class="shortcut-arrow" />
                </button>
              </div>
            </section>

            <section class="panel operating-panel">
              <div class="section-head"><div><span class="section-caption">BETRIEB</span><h2>Auf einen Blick</h2></div><span class="soft-tag">Nur Anzeige</span></div>
              <div class="operation-row">
                <div class="operation"><span class="operation-icon"><Power :size="24" /></span><span>Ein / Aus</span><strong>{{ powerText }}</strong></div>
                <div class="operation"><span class="operation-icon"><Sun :size="24" /></span><span>Modus</span><strong>{{ modeText }}</strong></div>
                <div class="operation"><span class="operation-icon"><VolumeX :size="24" /></span><span>Ruhemodus</span><strong>—</strong></div>
              </div>
              <button class="main-action" @click="navigate('parameters')"><SlidersHorizontal :size="19" /><span>Parameter & Einstellungen</span><ArrowRight :size="19" /></button>
              <p class="section-hint">Cloud-Livewerte werden bei sichtbarer Übersicht aktualisiert. Schreibfunktionen bleiben deaktiviert.</p>
            </section>
          </div>
          <section class="panel main-register-preview">
            <button class="register-preview-toggle" type="button" @click="mainRegisterOpen = !mainRegisterOpen"
              :aria-expanded="mainRegisterOpen">
              <span><span class="section-caption">REGISTER / FOXAIR_CONTROL</span><strong>Registerübersicht im Hauptfenster</strong></span>
              <span>{{ mainRegisterOpen ? 'Schließen' : 'Anzeigen' }} <ChevronRight :size="17" :class="{ 'is-open': mainRegisterOpen }" /></span>
            </button>
            <template v-if="mainRegisterOpen">
              <div class="register-preview-controls">
                <label class="search-box"><Search :size="17" /><input v-model="mainRegisterSearch" placeholder="Register oder Code suchen" aria-label="Hauptfenster Register filtern" /></label>
                <div class="parameter-groups">
                  <button v-for="grp in ['', 'T', 'H', 'P', 'R', 'D', 'E', 'SG', 'CLOUD']" :key="grp" class="group-chip"
                    :class="{ active: mainRegisterGroup === grp }" @click="mainRegisterGroup = grp">{{ grp || 'Alle' }}</button>
                </div>
              </div>
              <div class="main-register-list">
                <div v-for="entry in mainRegisterRows" :key="entry.code" class="main-register-row"
                  :class="{ 'is-stale': entry.quality === 'stale' }">
                  <span class="register-code">{{ entry.code }}</span>
                  <span class="register-title">{{ entry.name }}<small>{{ entry.register ?? 'Nur Cloud' }}</small></span>
                  <strong :title="relativeTimestamp(entry.timestamp)">{{ textValue(entry.value) }} {{ entry.unit }}</strong>
                </div>
                <p v-if="!mainRegisterRows.length" class="empty-state">Noch keine Registerwerte vorhanden.</p>
              </div>
              <button class="outlined-action" type="button" @click="navigate('parameters')">Alle Parameter öffnen <ArrowRight :size="16" /></button>
            </template>
          </section>
        </div>
      </template>

      <template v-else-if="page === 'parameters'">
        <section class="page-heading"><div><span class="section-caption">FOX AIR / TECHNIK</span><h1>Parameter & Einstellungen</h1><p>Register aus dem gemeinsamen FoxAir_Control-Katalog.</p></div><button class="back-link" @click="navigate('home')"><ArrowLeft :size="17" /> Übersicht</button></section>
        <div class="work-layout">
          <section class="panel register-list">
            <div class="source-tabs" role="group" aria-label="Register- oder Cloudansicht">
              <button type="button" :class="{ active: !cloudView }" @click="cloudView = false">Modbus-Register</button>
              <button type="button" :class="{ active: cloudView }" @click="cloudView = true">Alle Cloud-Codes <small>{{ cloudOverview?.total ?? 0 }}</small></button>
            </div>
            <label class="search-box"><Search :size="19" /><input v-model="search" placeholder="Code, Name oder Register suchen" aria-label="Parameter suchen" /></label>
            <div v-if="cloudView" class="scan-info">
              <strong>{{ cloudOverview?.supported ?? 0 }} / {{ cloudOverview?.total ?? 0 }} Codes mit Wert</strong>
              <span>Scan: {{ cloudOverview?.status === 'running' ? 'läuft (' + cloudOverview.progress + ')' : cloudOverview?.status || 'noch nicht gestartet' }}</span>
              <span v-if="cloudOverview?.error">{{ cloudOverview.error }}</span>
              <div class="parameter-groups">
                <button v-for="option in [{ id: '', name: 'Alle' }, { id: 'live', name: 'Live' }, { id: 'static', name: 'Konfiguration' }, { id: 'other', name: 'Weitere' }]"
                  :key="option.id" class="group-chip" :class="{ active: cloudKind === option.id }"
                  @click="cloudKind = option.id">{{ option.name }}</button>
              </div>
              <button type="button" class="outlined-action" @click="loadCloudValues"><RefreshCw :size="15" /> Cache aktualisieren</button>
            </div>
            <div v-if="!cloudView" class="parameter-groups" aria-label="Parametergruppen">
              <button type="button" class="group-chip" :class="{ active: selectedGroup === '' }" @click="selectedGroup = ''">Alle</button>
              <button v-for="group in registerGroups" :key="group.group" type="button"
                class="group-chip" :class="{ active: selectedGroup === group.group }"
                @click="selectedGroup = group.group">{{ group.group }} <small>{{ group.count }}</small></button>
            </div>
            <div v-if="!cloudView" class="register-toolbar"><span>{{ registerLoading ? 'Suche …' : registers.length + ' Treffer · ' + catalogSize + ' Register gesamt' }}</span><span>{{ transportLabel }}</span></div>
            <div v-if="!cloudView" class="register-items">
              <button v-for="entry in registers" :key="entry.register" class="register-item" :class="{ active: selectedRegister?.register === entry.register }" @click="selectRegister(entry)">
                <span class="register-code">{{ entry.code || entry.register }}</span>
                <span class="register-title">{{ entry.name }}<small>Register {{ entry.register }} <template v-if="entry.cloud?.code"> · Cloud {{ entry.cloud.code }}</template></small></span>
                <span class="register-measure" :class="{ unknown: currentCloudRegisterValue(entry.register)?.value == null }"
                  :title="relativeTimestamp(currentCloudRegisterValue(entry.register)?.timestamp)">
                  {{ textValue(currentCloudRegisterValue(entry.register)?.value ?? entry.cloud?.value) }}
                  <small>{{ currentCloudRegisterValue(entry.register)?.unit || entry.cloud?.unit || '' }}</small>
                </span>
                <ChevronRight :size="16" />
              </button>
              <p v-if="!registerLoading && !registers.length" class="empty-state">Keine passenden Register gefunden.</p>
            </div>
            <div v-else class="register-items">
              <button v-for="entry in filteredCloudRows" :key="entry.code" class="register-item"
                :class="{ active: cloudCodeSelected?.code === entry.code }" @click="cloudCodeSelected = entry">
                <span class="register-code">{{ entry.code }}</span>
                <span class="register-title">{{ entry.name }}
                  <small>{{ entry.register ? 'MAIN ' + entry.register : 'Nur Cloud' }} · {{ entry.kind }}</small></span>
                <span class="register-measure" :class="{ unknown: entry.value == null }" :title="relativeTimestamp(entry.timestamp)">
                  {{ textValue(entry.value) }}<small>{{ entry.unit }}</small>
                </span>
                <ChevronRight :size="16" />
              </button>
              <p v-if="!filteredCloudRows.length" class="empty-state">Keine passenden Cloud-Codes.</p>
            </div>
          </section>
          <section class="panel register-detail">
            <template v-if="cloudView && cloudCodeSelected">
              <span class="section-caption">CLOUD-CODE</span>
              <h2>{{ cloudCodeSelected.name }}</h2>
              <span class="register-code large">{{ cloudCodeSelected.code }}</span>
              <div class="detail-value">
                <span>Cloud-Wert</span>
                <strong>{{ textValue(cloudCodeSelected.value) }} <small>{{ cloudCodeSelected.unit }}</small></strong>
                <p>{{ relativeTimestamp(cloudCodeSelected.timestamp) }} · {{ cloudCodeSelected.quality }}</p>
              </div>
              <div class="detail-metadata">
                <span>MAIN-Zuordnung <strong>{{ cloudCodeSelected.register ?? 'nicht bestätigt' }}</strong></span>
                <span>Cloud-Kategorie <strong>{{ cloudCodeSelected.kind }}</strong></span>
                <span>Mapping-Confidence <strong>{{ cloudCodeSelected.confidence || 'unbekannt' }}</strong></span>
                <span>Unterstützung <strong>{{ cloudCodeSelected.supported ? 'Wert vorhanden' : 'kein Wert' }}</strong></span>
              </div>
              <p class="section-hint">Cloud-Originalwert in API-Skalierung; keine Umrechnung anhand lokaler Modbus-Rohwerte.</p>
            </template>
            <template v-else-if="!cloudView && selectedRegister">
              <span class="section-caption">PARAMETERDETAILS</span>
              <div class="detail-top"><div><span class="register-code large">{{ selectedRegister.code || 'MAIN' }}</span><h2>{{ selectedRegister.name }}</h2></div><Star :size="23" class="star-muted" /></div>
              <div class="detail-value"><span>Aktueller Wert</span>
                <strong>{{ textValue(currentValue?.value ?? currentCloudRegisterValue(selectedRegister.register)?.value ?? selectedRegister.cloud?.value) }}
                  <small>{{ currentValue?.unit || currentCloudRegisterValue(selectedRegister.register)?.unit || selectedRegister.cloud?.unit || '' }}</small></strong>
                <p>{{ relativeTimestamp(currentValue?.timestamp ?? currentCloudRegisterValue(selectedRegister.register)?.timestamp ?? selectedRegister.cloud?.timestamp) }}</p>
              </div>
              <div class="detail-metadata"><span>Modbus-Register <strong>{{ selectedRegister.register }}</strong></span><span>Gruppe <strong>{{ selectedRegister.group }}</strong></span><span>Typ <strong>{{ selectedRegister.type }}</strong></span><span>Zugriff <strong>{{ selectedRegister.mode }}</strong></span></div>
              <p class="description">{{ selectedRegister.description || 'Keine zusätzliche Beschreibung vorhanden.' }}</p>
              <p v-if="readError" class="read-error">{{ readError }}</p>
              <button class="main-action" :disabled="reading || !selectedTransportInfo?.read_supported" @click="readRegister"><RefreshCw :size="18" :class="{ spinning: reading }" />{{ reading ? 'Wert wird gelesen …' : 'Register jetzt lesen' }}</button>
              <p class="section-hint">Schreiben ist in diesem ersten Entwicklungsstand deaktiviert. {{ selectedTransportInfo?.read_supported ? '' : selectedTransportInfo?.reason || '' }}</p>
            </template>
            <div v-else class="empty-detail"><SlidersHorizontal :size="35" /><h2>{{ cloudView ? 'Cloud-Code auswählen' : 'Parameter auswählen' }}</h2><p>Die aktuellen Cloudwerte sind bereits in der Liste sichtbar. Für Details einen Eintrag öffnen.</p></div>
          </section>
        </div>
      </template>

      <template v-else>
        <section class="page-heading"><div><span class="section-caption">ANWENDUNG</span><h1>App-Einstellungen</h1><p>Verbindung und Anzeige für dieses Gerät.</p></div><button class="back-link" @click="navigate('home')"><ArrowLeft :size="17" /> Übersicht</button></section>
        <section class="settings-panel panel">
          <div class="section-head"><div><span class="section-caption">VERBINDUNG</span><h2>Transport auswählen</h2></div><ShieldCheck :size="24" /></div>
          <p>Deine letzte Auswahl wird auf diesem Gerät gespeichert. Sie öffnet keine dauerhafte Modbus-Verbindung.</p>
          <div class="transport-options">
            <label v-for="option in (transports.length ? transports : [
              { id: 'cloud', name: 'PHNIX Cloud', configured: false, read_supported: false, reason: '' },
              { id: 'standard_modbus', name: 'Standard-Modbus', configured: false, read_supported: false, reason: '' },
              { id: 'display_modbus', name: 'Display-Modbus', configured: false, read_supported: false, reason: '' },
              { id: 'warmlink_raw', name: 'LTE-/Warmlink-Modbus', configured: false, read_supported: false, reason: '' }
            ])" :key="option.id" class="transport-option" :class="{ active: selectedTransport === option.id }">
              <input v-model="selectedTransport" type="radio" name="transport" :value="option.id" />
              <span class="transport-option-icon"><Cloud v-if="option.id === 'cloud'" :size="21" /><Wifi v-else-if="option.id === 'standard_modbus'" :size="21" /><Gauge v-else-if="option.id === 'display_modbus'" :size="21" /><RadioTower v-else :size="21" /></span>
              <span class="transport-option-text"><strong>{{ option.name }}</strong><small>{{ option.read_supported ? 'Lesen verfügbar' : option.reason || 'Noch nicht konfiguriert' }}</small></span>
              <span class="choice-mark"></span>
            </label>
          </div>
          <div class="settings-note"><Activity :size="18" /><p>Cloud-Livepolling während sichtbarer Übersicht. Standard-Modbus bleibt aufgrund anderer Busnutzer standardmäßig deaktiviert. LTE-/Display-Anbindung folgt separat.</p></div>
          <button class="outlined-action" @click="loadDashboard(false)"><RefreshCw :size="17" /> Verbindung erneut prüfen</button>
        </section>
        <section class="settings-panel panel">
          <div class="section-head"><div><span class="section-caption">LIVEABFRAGE</span><h2>Cloud-Aktualisierung</h2></div><RefreshCw :size="22" /></div>
          <label class="settings-check"><input type="checkbox" v-model="liveEnabled" /> Automatisch aktualisieren, solange die Übersicht sichtbar ist</label>
          <label class="field-label" for="live-interval">Intervall (10–3600 Sekunden)</label>
          <input id="live-interval" class="settings-input" type="number" min="10" max="3600" v-model.number="liveInterval" @change="liveInterval = Math.max(10, Math.min(3600, Number(liveInterval) || 30))" />
          <p class="section-hint">Livepoll mit app_heartbeat=23205 und nachfolgendem Datenabruf. Kein regelmäßiges Polling in inaktiven Tabs.</p>
        </section>
        <section class="settings-panel panel cloud-panel">
          <div class="section-head"><div><span class="section-caption">PHNIX / WARMLINK</span><h2>Cloud-Zugang & Geräte</h2></div><Cloud :size="24" /></div>
          <p>Cloud: <strong>{{ cloudStatus?.configured ? 'eingerichtet' : 'nicht vollständig' }}</strong> · Benutzer {{ cloudStatus?.username_configured ? 'vorhanden' : 'fehlt' }} · Gerätekennung {{ cloudStatus?.device_configured ? 'vorhanden' : 'fehlt' }}</p>
          <p v-if="!cloudStatus?.admin_enabled" class="read-error">Web-Administration lokal einrichten: <code>python3 scripts/setup_web_admin.py</code></p>
          <p v-else-if="!secureAdminContext" class="read-error">Für die Cloud-Bearbeitung HTTPS oder einen lokalen SSH-Tunnel verwenden. Über unverschlüsseltes LAN-HTTP bleibt sie gesperrt.</p>
          <form class="cloud-form" @submit.prevent="saveCloudSettings">
            <label class="field-label" for="admin-password">Web-Administrationspasswort</label>
            <input id="admin-password" class="settings-input" v-model="cloudAdminPassword" type="password" autocomplete="off" placeholder="Lokal eingerichtet" :disabled="!secureAdminContext" />
            <button type="button" class="outlined-action account-load" :disabled="accountLoading || !cloudStatus?.admin_enabled || !secureAdminContext || !cloudAdminPassword" @click="loadStoredAccount">
              <ShieldCheck :size="17" /> {{ accountLoading ? 'Prüfe Adminzugang …' : 'Aktuelle E-Mail und Gerätekennung anzeigen' }}
            </button>
            <p v-if="accountLoaded" class="success-text">Gespeicherter Benutzer und deviceCode wurden in die beiden Felder unten übernommen. Das Cloud-Passwort bleibt verborgen.</p>
            <label class="field-label" for="cloud-username">WarmLink-Benutzername</label>
            <input id="cloud-username" class="settings-input" v-model="cloudUsername" autocomplete="off" placeholder="Leer = bisherigen Benutzer behalten" :disabled="!secureAdminContext" />
            <label class="field-label" for="cloud-password">Cloud-Passwort</label>
            <input id="cloud-password" class="settings-input" v-model="cloudPassword" type="password" autocomplete="new-password" placeholder="Leer = bisheriges Passwort behalten" :disabled="!secureAdminContext" />
            <label class="field-label" for="cloud-device">Gerätekennung (deviceCode)</label>
            <input id="cloud-device" class="settings-input" v-model="cloudDeviceCode" placeholder="Leer = bisherige Kennung behalten" :disabled="!secureAdminContext" />
            <button class="main-action" type="submit" :disabled="cloudSaving || !cloudStatus?.admin_enabled || !secureAdminContext || !cloudAdminPassword">{{ cloudSaving ? 'Speichert …' : 'Cloud-Einstellungen speichern' }}</button>
          </form>
          <div class="cloud-discovery">
            <button class="outlined-action" type="button" :disabled="cloudDiscovering || !cloudStatus?.admin_enabled || !secureAdminContext || !cloudAdminPassword" @click="discoverCloudDevices">
              <Search :size="17" /> {{ cloudDiscovering ? 'Suche läuft …' : 'Cloud-Geräte und Informationen abrufen' }}
            </button>
            <div v-if="cloudDevices.length" class="device-list">
              <button v-for="device in cloudDevices" :key="device.deviceCode" type="button" class="device-card" @click="cloudDeviceCode = device.deviceCode">
                <strong>{{ device.deviceNickName || device.deviceName || 'PHNIX-Gerät' }}</strong>
                <span>Modell: {{ device.model || device.custModel || '—' }}</span>
                <span>Status: {{ device.deviceStatus ?? '—' }} · Fehler: {{ device.isFault === undefined ? '—' : device.isFault ? 'Ja' : 'Nein' }}</span>
                <span>DTU-Version: {{ device.dtuSoftwareVer || '—' }} · Signal: {{ device.dtuSignalIntensity ?? '—' }}</span>
                <span v-if="device.houseName">Haus: {{ device.houseName }}</span>
                <small>Auswählen</small>
              </button>
            </div>
          </div>
          <div class="cloud-discovery">
            <button type="button" class="outlined-action" :disabled="cloudStatusLoading || !cloudStatus?.admin_enabled || !secureAdminContext || !cloudAdminPassword" @click="queryCloudDeviceStatus">
              <Activity :size="17" /> {{ cloudStatusLoading ? 'Frage Gerätestatus ab …' : 'Status des ausgewählten Cloud-Geräts abrufen' }}
            </button>
            <div v-if="Object.keys(selectedCloudStatus).length" class="device-status">
              <div v-for="(value, key) in selectedCloudStatus" :key="key"><span>{{ key }}</span><strong>{{ value ?? '—' }}</strong></div>
            </div>
          </div>
          <p v-if="cloudMessage" role="status" class="success-text">{{ cloudMessage }}</p>
          <p v-if="cloudError" role="alert" class="read-error">{{ cloudError }}</p>
          <div class="cloud-discovery">
            <button type="button" class="outlined-action" :disabled="cloudScanLoading || !cloudStatus?.admin_enabled || !secureAdminContext || !cloudAdminPassword" @click="rescanCloud">
              <RefreshCw :size="17" :class="{ spinning: cloudScanLoading }" /> Vollständigen Cloud-Katalog erneut abfragen
            </button>
            <p class="section-hint">{{ cloudOverview?.supported ?? 0 }} / {{ cloudOverview?.total ?? 0 }} Cloud-Codes mit Wert · Scanstatus: {{ cloudOverview?.status || 'unbekannt' }}</p>
          </div>
          <p class="section-hint">Geräteinformationen stammen aus Geräteliste und Hauszuordnungen. Cloud-Passwort und Token werden nicht aus dem Server ausgelesen.</p>
        </section>
        <section class="settings-panel panel">
          <div class="section-head"><div><span class="section-caption">VERSIONEN / GITHUB</span>
            <h2>FoxAir-Web aktualisieren</h2></div><RefreshCw :size="22" /></div>
          <p class="section-hint">Der Update-Hilfsdienst aktualisiert ausschließlich FoxAir-Web von GitHub und verwendet denselben geprüften Build wie <code>scripts/update.sh</code>. Er wird einmalig im LXC installiert.</p>
          <div class="update-versions">
            <div><span>Installierter Commit</span><strong>{{ updateInfo?.current?.slice(0, 10) || '—' }}</strong></div>
            <div><span>GitHub main</span><strong>{{ updateInfo?.remote?.slice(0, 10) || 'nicht erreichbar' }}</strong></div>
            <div><span>Aktiver Web-Build</span><strong>{{ updateInfo?.deployed?.slice(0, 10) || 'unbekannt' }}</strong></div>
            <div><span>Hilfsdienst</span><strong>{{ updateInfo?.installed ? 'Bereit' : 'Nicht eingerichtet' }}</strong></div>
            <div><span>Status</span><strong>{{ updateInfo?.running ? 'Update läuft' : updateInfo?.pending ? 'Anforderung wartet' : updateInfo?.last_result || '—' }}</strong></div>
          </div>
          <p v-if="updateInfo?.update_available" class="success-text">Update erforderlich oder aktiver Web-Build ist noch nicht synchronisiert.</p>
          <p v-else-if="updateInfo?.remote && updateInfo?.current === updateInfo?.remote" class="section-hint">Installierter Code entspricht dem aktuellen main-Commit.</p>
          <p v-if="!updateInfo?.installed" class="section-hint">Einmalig als root im LXC: <code>bash scripts/install_web_update.sh</code></p>
          <div class="update-actions">
            <button type="button" class="outlined-action" :disabled="updateLoading" @click="loadGitUpdateStatus">
              <RefreshCw :size="16" :class="{ spinning: updateLoading }" /> GitHub-Version prüfen
            </button>
            <button type="button" class="main-action" :disabled="!updateInfo?.installed || updateInfo?.running || updateInfo?.pending || !cloudAdminPassword || !secureAdminContext || updateRequesting" @click="submitGitUpdate">
              <RefreshCw :size="16" :class="{ spinning: updateRequesting }" />
              {{ updateRequesting ? 'Fordere Update an …' : 'Jetzt über GitHub aktualisieren' }}
            </button>
          </div>
          <p v-if="updateMessage" class="success-text">{{ updateMessage }}</p>
          <p v-if="updateError" class="read-error">{{ updateError }}</p>
          <p class="section-hint">Für den Update-Knopf das Administrationspasswort im Bereich „Cloud-Zugang & Geräte“ eingeben. Keine Updates ohne autorisierte Anforderung; ein echter Installationserfolg wird erst anhand der nächsten Statusprüfung angezeigt.</p>
        </section>
        <section class="settings-panel panel">
          <div class="section-head">
            <div><span class="section-caption">DIAGNOSE</span><h2>Cloud-Protokoll</h2></div>
            <button type="button" class="outlined-action" @click="loadCloudLogs"><RefreshCw :size="16" /> Aktualisieren</button>
          </div>
          <p class="section-hint">Letzte Ereignisse aus dem laufenden Webserver: Login-/Lese- und Scanstatus, ohne Zugangsdaten, Tokens oder Gerätekennungen. Das Protokoll wird beim Dienstneustart zurückgesetzt.</p>
          <div class="cloud-log-list">
            <div v-for="(entry, index) in cloudLogs" :key="index" class="cloud-log-item">
              <time>{{ new Date(entry.time).toLocaleString('de-DE') }}</time>
              <span class="cloud-log-kind" :class="entry.kind">{{ entry.kind }}</span>
              <span>{{ entry.message }} <template v-if="entry.count !== undefined">({{ entry.count }})</template></span>
            </div>
            <p v-if="!cloudLogs.length" class="empty-state">Noch keine Cloud-Ereignisse aufgezeichnet.</p>
          </div>
        </section>
      </template>
    </main>

    <div v-if="specialDialog" class="special-overlay" @click.self="specialDialog = null">
      <section class="special-modal panel" role="dialog" aria-modal="true" aria-labelledby="special-modal-title">
        <div class="special-top">
          <div><span class="section-caption">FOX AIR / CLOUD</span>
            <h2 id="special-modal-title">{{ selectedSpecial?.title || 'Spezialdialog' }}</h2>
            <p>{{ selectedSpecial?.description }}</p></div>
          <button type="button" class="outlined-action" aria-label="Dialog schließen" @click="specialDialog = null">Schließen</button>
        </div>
        <p class="section-hint">Anzeige der bekannten Cloud-Werte wie in FoxAir_Control. Schreiben ist in dieser Entwicklungsstufe absichtlich deaktiviert.</p>
        <div class="special-toolbar">
          <button type="button" class="outlined-action" :disabled="specialLoading" @click="refreshSelectedSpecial">
            <RefreshCw :size="16" :class="{ spinning: specialLoading }" />
            {{ specialLoading ? 'Frage Cloudwerte ab …' : 'Cloudwerte neu abfragen' }}
          </button>
          <span>{{ specialRows.filter(row => row.value !== null).length }} / {{ specialRows.length }} mit Wert</span>
        </div>
        <p v-if="specialMessage" role="status" class="success-text">{{ specialMessage }}</p>
        <p v-if="specialError" role="alert" class="read-error">{{ specialError }}</p>
        <div class="special-rows">
          <div v-for="entry in specialRows" :key="entry.code" class="main-register-row"
            :class="{ 'is-stale': entry.quality === 'stale' }">
            <span class="register-code">{{ entry.code }}</span>
            <span class="register-title">{{ entry.name }}
              <small>{{ entry.register != null ? 'MAIN ' + entry.register : 'Nur Cloud' }}</small>
            </span>
            <strong :title="relativeTimestamp(entry.timestamp)">{{ textValue(entry.value) }} {{ entry.unit }}</strong>
          </div>
          <p v-if="!specialRows.length" class="empty-state">Keine passenden Cloud-Codes im Katalog.</p>
        </div>
      </section>
    </div>

    <nav class="mobile-bottom" aria-label="Mobilnavigation">
      <button :class="{ active: page === 'home' }" @click="navigate('home')"><House :size="21" /><span>Übersicht</span></button>
      <button :class="{ active: page === 'parameters' }" @click="navigate('parameters')"><SlidersHorizontal :size="21" /><span>Parameter</span></button>
      <button :class="{ active: page === 'settings' }" @click="navigate('settings')"><Settings2 :size="21" /><span>Mehr</span></button>
    </nav>
  </div>
</template>
