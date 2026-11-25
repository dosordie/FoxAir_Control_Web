<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Activity, ArrowLeft, ArrowRight, Bell,
  ChevronRight, Clock3, Cloud, Gauge, HeartPulse, House,
  Power, RadioTower, RefreshCw,
  Settings2, SlidersHorizontal, Star,
  Sun, Thermometer, VolumeX, Wifi, Zap
} from 'lucide-vue-next'
import TimerEditor from './TimerEditor.vue'
import CloudInsights from './CloudInsights.vue'
import { useSharedTransport } from './composables/useSharedTransport'
import { useUpdateStatus } from './composables/useUpdateStatus'
import { useAdminSession } from './composables/useAdminSession'
import AppHeader from './components/AppHeader.vue'
import UpdatePanel from './components/UpdatePanel.vue'
import ConnectionSettingsDialog from './components/ConnectionSettingsDialog.vue'
import ParameterEditor from './components/ParameterEditor.vue'
import CompressorGauge from './components/CompressorGauge.vue'
import OverviewSettings from './components/OverviewSettings.vue'
import LocalHistory from './components/LocalHistory.vue'
import { giraIcon } from './giraIcons'
import { formatGiraValue, isGiraText } from './giraValues'
import { defaultOverview, overviewFields, type OverviewField, type OverviewLayout } from './overview'
import type { CameraSettings, GiraItem } from './api'
import { useTimerSummary } from './composables/useTimerSummary'
import RegisterDecoder from './components/RegisterDecoder.vue'
import PowerSummary from './components/PowerSummary.vue'
import HeatpumpStatus from './components/HeatpumpStatus.vue'
import ExpertGira from './components/ExpertGira.vue'
import CameraDialog from './components/CameraDialog.vue'
import OperationDialog from './components/OperationDialog.vue'
import TargetEditorDialog from './components/TargetEditorDialog.vue'
import { useDashboardPolling } from './composables/useDashboardPolling'
import ExpertCamera from './components/ExpertCamera.vue'
import SetupWizard from './components/SetupWizard.vue'
import MainRegisterBrowser from './components/MainRegisterBrowser.vue'
import SpecialControls from './components/SpecialControls.vue'
import AccountManagement from './components/AccountManagement.vue'
import LanAccessSettings from './components/LanAccessSettings.vue'
import ParameterFilters from './components/ParameterFilters.vue'
import ParameterDetails from './components/ParameterDetails.vue'
import LteScanSummary from './components/LteScanSummary.vue'
import ParameterValue from './components/ParameterValue.vue'
import type { Page } from './types/navigation'
import { useRegisterFavorites } from './composables/useRegisterFavorites'
import { useRegisterCatalog } from './composables/useRegisterCatalog'
import { useLteConnection } from './composables/useLteConnection'
import { useBrowserConnection } from './composables/useBrowserConnection'
import { api } from './api'
import { fanIsRunning } from './telemetry'
import type { CloudRow, CloudLog, CloudValues, Dashboard, Metric, Register, RegisterValue, SpecialDialog, Transport, TransportId } from './api'

const { browserOnline } = useBrowserConnection()
const { selectedTransport, transportPaused, setTransportPaused, transportBusy, transportError, initializeTransport } = useSharedTransport()
const transports = ref<Transport[]>([])
const page = ref<Page>('home')
const { snapshot, refreshing, error, liveEnabled, liveInterval, loadDashboard, scheduleRefresh, stopRefresh } =
  useDashboardPolling(selectedTransport, page, loadLastValues, loadCloudValues)
const cloudRows = ref<CloudRow[]>([])
const cloudOverview = ref<CloudValues | null>(null)
const cloudLogs = ref<CloudLog[]>([])
const specialDialogs = ref<SpecialDialog[]>([])
const specialDialog = ref<string | null>(null)
const specialDialogElement = ref<HTMLDialogElement|null>(null)
watch(specialDialog, async id => {
  await nextTick()
  const dialog=specialDialogElement.value
  if(id && dialog && !dialog.open) dialog.showModal()
  else if(!id && dialog?.open) dialog.close()
})
const specialLoading = ref(false)
const specialError = ref('')
const specialMessage = ref('')
const selectedSpecial = computed(() => specialDialogs.value.find(x => x.id === specialDialog.value) || null)
const specialRows = computed(() => {
  if (selectedTransport.value !== 'cloud') return []
  const selected = selectedSpecial.value
  if (!selected) return []
  const byCode = new Map(cloudRows.value.map(row => [row.code, row]))
  return selected.codes.map(code => byCode.get(code)).filter((row): row is CloudRow => !!row)
})
const parameterDetails = ref<InstanceType<typeof ParameterDetails> | null>(null)
function selectCloudParameter(entry: CloudRow) {
  cloudCodeSelected.value = entry
  void parameterDetails.value?.open()
}
const cloudView = ref(false)
const cloudKind = ref('')
const cloudCodeSelected = ref<CloudRow | null>(null)
let valuesTimer: ReturnType<typeof setTimeout> | undefined
const deviceName = computed(() => snapshot.value?.device_name || 'FoxAir')
const { status: updateStatus, version: installedVersion, loading: updateLoading, error: updateCheckError, checkedAt: updateCheckedAt, refresh: refreshUpdateStatus } = useUpdateStatus()
const { signedIn, sessionChecked, username, sessionUsername, role, canOperate, ssoAvailable, loginWithSso, secureAdminContext, adminAuthenticated, adminBusy, loginOpen, cloudAdminPassword, adminLoginError, checkAdminSession, loginAsAdmin, logoutAsAdmin } = useAdminSession()
const cameraConfig = ref<CameraSettings>()
const cameraDialog = ref<InstanceType<typeof CameraDialog> | null>(null)
const canOpenCamera = computed(() =>
  !!cameraConfig.value?.enabled && signedIn.value && browserOnline.value && !transportPaused.value)
watch([signedIn, browserOnline], async ([active, online], _, cleanup) => {
  let current = true
  cleanup(() => { current = false })
  cameraConfig.value = undefined
  if (!active || !online) return
  try {
    const config = await api.cameraSettings()
    if (current) cameraConfig.value = config
  } catch {
    // The camera remains unavailable until settings can be read.
  }
}, { immediate: true })

watch(signedIn, (active) => { if (active) void refreshUpdateStatus() })

const operationDialog = ref<InstanceType<typeof OperationDialog> | null>(null)
const connectionSettingsOpen = ref(false)
const overviewLayout = ref<OverviewLayout>(defaultOverview)
const giraItems = ref<GiraItem[]>([])
const giraRevision = ref(0)
const glance = computed(() => overviewLayout.value[mobileProfile ? 'mobile_glance' : 'desktop_glance'])
const glanceOrder = computed(() => glance.value.filter(key => !key.startsWith('gira:') || !glance.value.includes('gira')))
const metricColumns = computed(() => mobileProfile ? overviewLayout.value.mobile_columns : overviewLayout.value.desktop_columns)
const mobileProfile = /iPhone|iPod|Android.*Mobile/i.test(navigator.userAgent)
async function loadOverview() {
  try {
    const layout = await api.overview()
    if (Array.isArray(layout.mobile) && Array.isArray(layout.desktop)) overviewLayout.value = { ...defaultOverview, ...layout }
  } catch { /* Retain the available layout during a connection interruption. */ }
}
const targetEditor = ref<InstanceType<typeof TargetEditorDialog> | null>(null)
const canEditTarget = computed(() => !transportPaused.value && canOperate.value && browserOnline.value &&
  secureAdminContext.value && selectedTransport.value !== 'display_modbus')
const historyOpen=ref(false)
const historyDialogElement=ref<HTMLDialogElement|null>(null)
watch(historyOpen, async opened=>{
  await nextTick()
  const dialog=historyDialogElement.value
  if(opened && dialog && !dialog.open)dialog.showModal()
  else if(!opened && dialog?.open)dialog.close()
})

const { busState, localValues, lteScan, pushConnected, scanStarting, startLteScan, refreshSnapshot } = useLteConnection(
  selectedTransport, snapshot, () => { currentValue.value = null },
)
let unmounted = false
const { favoriteIds, favoritesOnly, isFavorite, toggleFavorite } = useRegisterFavorites()
const activeFavorites = computed(() => favoritesOnly.value ? favoriteIds.value : undefined)
function toggleFavoriteFilter() {
  favoritesOnly.value = !favoritesOnly.value
  selectedGroup.value = ''; search.value = ''
}
const { search, selectedGroup, registers, catalogSize, registerLoading, catalogError, orderedGroups } = useRegisterCatalog(
  selectedTransport, page, () => { selectedRegister.value = null }, activeFavorites,
)
const selectedRegister = ref<Register | null>(null)
const reading = ref(false)
const currentValue = ref<RegisterValue | null>(null)
const readError = ref('')

const selectedTransportInfo = computed(() => transports.value.find(t => t.id === selectedTransport.value))
const transportLabel = computed(() => selectedTransportInfo.value?.name || 'Cloud')
const isBusTransport = computed(() => ['warmlink_raw','display_modbus'].includes(selectedTransport.value))
const busConnectionNote = computed(() => {
  const state = busState.value
  if (state?.error) return state.error
  if (!state?.connected) return 'Busverbindung wird geprüft …'
  if (!state.last_rx && selectedTransport.value === 'display_modbus') return 'Bus verbunden · lauscht auf Display-Telegramme'
  if (!pushConnected.value) return 'Bus verbunden · Live-Übertragung verbindet …'
  return 'Live · Bus verbunden'
})
const online = computed(() => isBusTransport.value ? !!busState.value?.connected : snapshot.value?.status === 'online')
const connectionText = computed(() => isBusTransport.value
  ? busState.value?.connected ? (busState.value.last_rx ? 'Verbunden' : 'Bus verbunden · wartet auf Werte') : 'Nicht verbunden'
  : online.value ? 'Verbunden' : snapshot.value?.status === 'partial' ? 'Messwerte unvollständig' : 'Nicht verbunden')
const modeText = computed(() => displayMetric(snapshot.value?.metrics.mode || null, '—'))
const powerText = computed(() => displayMetric(snapshot.value?.metrics.power || null, '—'))
const fanRunning = computed(() => fanIsRunning(
  snapshot.value?.metrics.power || null,
  snapshot.value?.metrics.compressor_frequency || null,
  [currentRegisterValue(2074), currentRegisterValue(2075)],
))
const supplyDelta = computed(() => {
  const data = snapshot.value?.metrics
  if (!data || snapshot.value?.status === 'unavailable' ||
      data.target?.quality === 'stale' || data.supply?.quality === 'stale' ||
      data.target?.source_code !== '2014') return null
  const target = Number(String(data.target.value).replace(',', '.'))
  const supply = Number(String(data.supply?.value ?? '').replace(',', '.'))
  return Number.isFinite(target) && data.supply != null && Number.isFinite(supply)
    ? Math.round((supply - target) * 10) / 10 : null
})
const deltaTone = computed(() => supplyDelta.value == null ? 'neutral' : supplyDelta.value <= -0.3 ? 'cold' : supplyDelta.value >= 0.3 ? 'warm' : 'neutral')
const waterSpread = computed(() => {
  const data = snapshot.value?.metrics
  if (!data || snapshot.value?.status === 'unavailable' || !data.supply || !data.return ||
      data.supply.quality === 'stale' || data.return.quality === 'stale') return null
  const supply = Number(String(data.supply.value).replace(',', '.'))
  const waterReturn = Number(String(data.return.value).replace(',', '.'))
  return Number.isFinite(supply) && Number.isFinite(waterReturn)
    ? Math.round((supply - waterReturn) * 10) / 10 : null
})
function deltaText(value: number | null): string {
  return value === null ? '—' : (value > 0 ? '+' : '') + value.toLocaleString('de-DE', {maximumFractionDigits:1})
}
const browserRows = computed(() => {
  const names = new Map(cloudRows.value.filter(row => row.register != null).map(row => [row.register!, row]))
  const values = ['warmlink_raw','display_modbus'].includes(selectedTransport.value)
    ? Object.values(localValues.value)
    : selectedTransport.value === 'standard_modbus'
      ? Object.values(sharedValues.value).filter(row => row.transport === 'standard_modbus')
      : cloudRows.value.filter(row => row.register != null && row.timestamp && row.value != null && row.confidence === 'confirmed')
          .map(row => ({...row, register: row.register!, raw:null, timestamp:row.timestamp!, value:row.value!, transport:'cloud'}))
  return values.map(row => ({...row, name:row.name || names.get(row.register)?.name || 'Register '+row.register}))
})
const filteredCloudRows = computed(() => {
  const term = search.value.trim().toLowerCase()
  return cloudRows.value.filter(row => {
    if (cloudKind.value && row.kind !== cloudKind.value) return false
    return !term || [row.code, row.name, String(row.register ?? ''), row.group]
      .some(part => part.toLowerCase().includes(term))
  }).sort((a, b) =>
    a.code.localeCompare(b.code, 'de', { numeric: true })
  )
})

const cloudByRegister = computed(() => {
  const result = new Map<number, CloudRow>()
  for (const item of cloudRows.value) {
    if (item.register == null || item.value === null || item.confidence !== 'confirmed') continue
    const current = result.get(item.register)
    if (!current || (item.confidence === 'confirmed' && current.confidence !== 'confirmed')) {
      result.set(item.register, item)
    }
  }
  return result
})
const sharedValues = ref<Record<string, RegisterValue>>({})
async function loadLastValues() {
  try { sharedValues.value = (await api.lastValues()).values } catch { /* Keep values until the server is reachable. */ }
}
function currentRegisterValue(register: number): RegisterValue | null {
  const direct = currentValue.value?.register === register && currentValue.value.transport === selectedTransport.value ? currentValue.value : null
  const local = ['warmlink_raw','display_modbus'].includes(selectedTransport.value) ? localValues.value[String(register)] : null
  const cloud = selectedTransport.value === 'cloud' ? cloudByRegister.value.get(register) : null
  const cloudValue = cloud?.timestamp && cloud.value != null ? {...cloud, register, raw:null, transport:'cloud', timestamp:cloud.timestamp, value:cloud.value} : null
  const last = sharedValues.value[String(register)]
  const groupValue = registers.value.find(r=>r.register===register)?.last
  return [direct, local, cloudValue, last, groupValue].filter((v):v is RegisterValue=>!!v)
    .sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp))[0] || null
}
function valueSource(register: number) {
  const row = currentRegisterValue(register)
  return row ? ({cloud:'Cloud', warmlink_raw:'Modbus (LTE)', standard_modbus:'Modbus', display_modbus:'Display-Bus'}[row.transport] || row.transport) : 'Noch kein Wert'
}
watch(selectedTransport, () => void loadLastValues())
onMounted(() => void loadLastValues())
function textValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}
function relativeTimestamp(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString('de-DE') : 'Noch kein Messwert'
}

const connectionClock = ref(Date.now())
let connectionClockTimer: ReturnType<typeof setInterval> | undefined
const longValuePause = computed(() => {
  if (transportPaused.value) return false
  const selected = selectedTransport.value
  const rows = [...Object.values(sharedValues.value), ...Object.values(localValues.value)]
  const latest = rows.reduce((stamp,row) => {
    const time = Date.parse(row.timestamp)
    return row.transport === selected && Number.isFinite(time) ? Math.max(stamp,time) : stamp
  }, 0)
  return latest > 0 && connectionClock.value - latest > 30 * 60 * 1000
})
const lastUpdated = computed(() => {
  if (!snapshot.value?.timestamp) return 'Noch keine Messwerte'
  if (snapshot.value.status === 'unavailable') {
    const last = Object.values(snapshot.value.metrics)
      .find(v => v && ['stale', 'cached'].includes(v.quality))
    return last?.timestamp ? 'Verbindung unterbrochen · letzter Messwert ' +
      new Date(last.timestamp).toLocaleString('de-DE') : 'Verbindung unterbrochen'
  }
  if(snapshot.value.transport==='warmlink_raw'){
    const latest=Object.values(snapshot.value.metrics).filter(v=>v&&v.quality!=='stale')
      .sort((a,b)=>Date.parse(b!.timestamp)-Date.parse(a!.timestamp))[0]
    if(latest)return (latest.quality==='observed'?'Letzter Buswert ':'Letzter Messwert ')+new Date(latest.timestamp).toLocaleTimeString('de-DE')
  }
  const observed=Object.values(snapshot.value.metrics).filter(v=>v?.quality==='observed')
    .map(v=>Date.parse(v!.timestamp)).sort((a,b)=>b-a)[0]
  if(observed)return 'Letzter Buswert ' + new Date(observed).toLocaleTimeString('de-DE')
  return 'Abfrage ' + new Date(snapshot.value.timestamp).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})
const actionButtons = [
  { label: 'Timer', hint: 'Zeitprogramme', icon: Clock3, color: 'apricot', dialog: 'timer' },
  { label: 'SG-Ready', hint: 'PV-Steuerung', icon: Zap, color: 'mint', dialog: 'sg' },
  { label: 'AT-Kurve', hint: 'Heizkennlinie', icon: Sun, color: 'lilac', dialog: 'at' },
  { label: 'Wärmepumpe', hint: 'Sollwerte', icon: Thermometer, color: 'mint', dialog: 'wp' },
  { label: 'Ruhemodus', hint: 'Silent-Timer', icon: VolumeX, color: 'apricot', dialog: 'silent' },
  { label: 'Schalterzustände', hint: 'Lastausgänge und Schalter', icon: SlidersHorizontal, color: 'mint', dialog: 'decoder' },
  { label: 'Störungen', hint: 'Fehlerstatus', icon: Bell, color: 'lilac', dialog: 'fault' },
]
const pumpPwm = computed(() => {
  const row = snapshot.value?.metrics.pump_pwm || currentRegisterValue(2115)
  const value = row == null ? NaN : Number(row.value)
  return Number.isFinite(value) && value >= 0 && value <= 100 ? row : null
})
function readingHint(key: string) {
  const hints: Record<string,string> = {flow:'Volumenstrom des Heizwassers. Die Pumpen-PWM zeigt die gemeldete Ansteuerung aus Register 2115; bei ausgeschalteter Pumpe kann der Registerwert trotzdem 100 % sein.',tank:'Temperatur im Warmwasserspeicher.',outdoor:'Gemessene Außentemperatur.',return:'Eintritt des Heizwassers in die Wärmepumpe (Rücklauf).',supply:'Austritt des erwärmten Heizwassers aus der Wärmepumpe (Vorlauf).'}
  return hints[key] || ''
}
const m1Selected = computed(() =>
  overviewLayout.value[mobileProfile ? 'mobile' : 'desktop'].includes('timer_m1') || glance.value.includes('timer_m1'))
const { m1Limit, m1Status, m1InWindow } =
  useTimerSummary(page, selectedTransport, transportPaused, m1Selected)
const readings = computed(() => {
  const keys = overviewLayout.value[mobileProfile ? 'mobile' : 'desktop']
  return keys.flatMap(key => {
    if (key.startsWith('gira:')) {
      const item = giraItems.value.find(row => row.layout_key === key)
      return [{ key, label: item?.name || '', unit: item?.unit || '', icon: giraIcon(item?.icon),
        text: formatGiraValue(item?.value, item?.decimals),
        compactText: isGiraText(item?.value),
        stale: item?.quality === 'stale' }]
    }
    if (!Object.hasOwn(overviewFields, key)) return []
    const field = key as OverviewField
    if (field === 'timer_m1') return [{ key, ...overviewFields[field], stale: m1Limit.value?.stale === true,
      compactText: false, text: m1Limit.value?.max_kw?.toLocaleString('de-DE', { maximumFractionDigits: 1 }) ?? '—' }]
    const row = field === 'spread' ? null : snapshot.value?.metrics[field]
    const stale = field === 'spread'
      ? snapshot.value?.metrics.return?.quality === 'stale' || snapshot.value?.metrics.supply?.quality === 'stale'
      : row?.quality === 'stale'
    return [{ key, ...overviewFields[field], stale, compactText: false,
      text: field === 'spread' ? deltaText(waterSpread.value) : displayMetric(row ?? null) }]
  })
})

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
  }
}
function navigate(target: Page, term = '') {
  if (target === 'parameters' && term) search.value = term
  window.location.hash = target === 'home' ? '#/' : '#/' + target
  syncRoute()
  if (target === 'parameters') {
    void loadCloudValues()
  }
}
function onVisibilityChange() {
  if(['warmlink_raw','display_modbus'].includes(selectedTransport.value)){
    if(!document.hidden && !pushConnected.value)void refreshSnapshot().catch(()=>{})
    return
  }
  stopRefresh()
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
  if (selectedTransport.value !== 'cloud') return
  try {
    void loadLastValues()
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
  if(dialog==='timer'||dialog==='silent')return
  if (selectedTransport.value === 'cloud') await loadCloudValues()
  void refreshSelectedSpecial()
}
async function refreshSelectedSpecial() {
  const id = specialDialog.value
  if (!id || specialLoading.value || transportPaused.value) return
  specialLoading.value = true
  specialError.value = ''
  specialMessage.value = ''
  try {
    if (selectedTransport.value !== 'cloud') {
      const transport = selectedTransport.value
      const registers = selectedSpecial.value?.local_registers || []
      if (!registers.length) { specialMessage.value = 'Für diesen Dialog sind keine lokalen Register hinterlegt.'; return }
      const result = await api.refreshParameters(transport, registers)
      if (selectedTransport.value !== transport || specialDialog.value !== id) return
      if (result.status === 'passive') await loadLastValues()
      else sharedValues.value = result.values
      if (transport === 'warmlink_raw') await refreshSnapshot()
      const received = registers.filter(register => result.values[String(register)]?.transport === transport).length
      specialMessage.value = result.status === 'passive'
        ? received + ' von ' + registers.length + ' über Display empfangen · übrige aus dem Wertespeicher, sofern vorhanden'
        : result.updated + ' Werte gelesen · ' + received + ' von ' + registers.length + ' verfügbar'
      return
    }
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




async function reloadTransportOptions(source: TransportId) {
  try {
    transports.value = (await api.transports()).items
    if(source==='cloud'&&selectedTransport.value==='cloud')void loadDashboard()
  } catch { error.value = 'Verbindungsübersicht konnte nicht aktualisiert werden.' }
}
function selectRegister(item: Register) {
  void parameterDetails.value?.open()
  selectedRegister.value = item
  currentValue.value = null
  readError.value = ''
}
let parameterReadGeneration = 0
async function readRegister() {
  const register = selectedRegister.value?.register
  if (!register) return
  const source = selectedTransport.value
  const generation = ++parameterReadGeneration
  const current = () => generation === parameterReadGeneration && selectedRegister.value?.register === register && selectedTransport.value === source
  reading.value = true
  readError.value = ''
  try {
    const row = await api.read(register, source)
    if (!current()) return
    currentValue.value = row
    void loadLastValues()
  } catch (err) {
    if (current()) readError.value = err instanceof Error ? err.message : 'Lesefehler'
  } finally {
    if (generation === parameterReadGeneration) reading.value = false
  }
}
watch(page, async (value) => {
  if (value === 'home' || value === 'settings') void loadOverview()
})
watch(selectedTransport, () => {
  currentValue.value = null
  if (selectedRegister.value) selectedRegister.value = {...selectedRegister.value, cloud: null}
})
watch([page,selectedTransport],([current,transport],[previous,previousTransport])=>{
  if(current==='parameters' && transport==='warmlink_raw' && (current!==previous || transport!==previousTransport))void startLteScan()
})
onMounted(async () => {
  syncRoute()
  const session = checkAdminSession()
  void loadOverview()
  connectionClockTimer = setInterval(() => { connectionClock.value = Date.now() }, 60000)
  window.addEventListener('hashchange', syncRoute)
  document.addEventListener('visibilitychange', onVisibilityChange)
  document.addEventListener('keydown', closeSpecialOnEscape)
  try {
    const response = await api.transports()
    transports.value = response.items
  } catch {
    // Backend not reachable; show unavailable values, never demo values.
  }
  await initializeTransport()
  await Promise.all([loadDashboard(), loadCloudValues(), session])
  try { specialDialogs.value = (await api.specialDialogs()).items } catch { specialDialogs.value = [] }
  if (page.value === 'settings') await loadCloudLogs()
  scheduleRefresh()
  scheduleValueRefresh()
})
onBeforeUnmount(() => {
  unmounted = true
  window.removeEventListener('hashchange', syncRoute)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  document.removeEventListener('keydown', closeSpecialOnEscape)
  clearTimeout(valuesTimer)
  clearInterval(connectionClockTimer)
  cloudAdminPassword.value = ''
})
</script>

<template>
  <div class="app-shell">
    <SetupWizard @completed="checkAdminSession().then(() => { loginOpen = !signedIn })" />
    <AppHeader :version="installedVersion" :update-available="updateStatus?.update_available" v-model:username="username" :session-username="sessionUsername" :role="role" :sso-available="ssoAvailable" @sso-login="loginWithSso" :page="page" :authenticated="signedIn" :busy="adminBusy" :secure="secureAdminContext" :error="adminLoginError"
      v-model:password="cloudAdminPassword" v-model:login-open="loginOpen" @navigate="navigate" @login="loginAsAdmin" @logout="logoutAsAdmin" />

    <main>
      <aside v-if="!browserOnline" class="notice" role="status">Offline – die Oberfläche ist verfügbar. Messwerte und Änderungen benötigen eine Verbindung zum Server.</aside>
      <template v-if="page === 'home'">
        <section class="heat-hero" :class="{ 'heat-hero-off': powerText === 'Aus' }">
          <div class="room-illustration" aria-hidden="true"><i></i><i></i><i></i></div>
          <div class="hero-content">
            <div class="hero-top">
              <div class="device-name"><h1>{{ deviceName }}</h1></div>
              <div class="connection">
                <span class="connection-dot" :class="{ online }"></span>
                <span>{{ connectionText }}</span>
              </div>
            </div>
            <div class="hero-main">
              <div class="unit-container" aria-label="Illustration einer Wärmepumpe">
                <div class="unit illustrated-unit">
                  <img class="heatpump-art" src="/foxair-heatpump-transparent.png" alt="FoxAir-Wärmepumpe mit Fuchsmotiv" />
                  <div class="fan-ring integrated-fan" :class="{ 'fan-running': fanRunning }" :aria-label="fanRunning?'Lüfter dreht':'Lüfter steht'">
                    <svg class="fan-rotor" viewBox="0 0 100 100" aria-hidden="true"><defs><linearGradient id="rotor-metal" x2="1" y2="1"><stop stop-color="#a6a9ac"/><stop offset=".5" stop-color="#343b40"/><stop offset="1" stop-color="#717a80"/></linearGradient></defs><g fill="url(#rotor-metal)" stroke="#1b2024" stroke-width=".6"><path v-for="rotation in [0,90,180,270]" :key="rotation" :transform="'rotate('+rotation+' 50 50)'" d="M49 48 C27 46 14 34 21 18 C35 8 52 19 56 37 L54 48Z"/></g><circle cx="50" cy="50" r="10" fill="#50585e" stroke="#828a90"/><circle cx="50" cy="50" r="3" fill="#252b30"/></svg>
                  </div>
                  <button v-if="canOpenCamera" class="heatpump-camera-trigger" type="button"
                    aria-label="Kamerabild der Wärmepumpe öffnen" title="Kamerabild öffnen" @click="cameraDialog?.open()"></button>
                  <HeatpumpStatus :mode="currentRegisterValue(1012)" :run="currentRegisterValue(2012)" :power="snapshot?.metrics.power || null" />

                </div>
                <CompressorGauge :metric="snapshot?.metrics.compressor_frequency || null" />
              </div>
              <div class="target-temperature">
                <span class="overline" title="Aktuell von der Regelung gewählter Wassersollwert (Register 2014), einschließlich aktiver Wetterkompensation.">Aktueller Sollwert</span>
                <button v-if="canEditTarget" type="button" class="temp-adjust target-edit" aria-label="Heizungs-Basissollwert einstellen" @click="targetEditor?.open()">
                  <strong>{{ metric('target') }}<small v-if="snapshot?.metrics.target"> °C</small></strong>
                </button>
                <div v-else class="temp-adjust target-readonly">
                  <strong>{{ metric('target') }}<small v-if="snapshot?.metrics.target"> °C</small></strong>
                </div>
                <span class="target-delta" :class="'delta-' + deltaTone" title="Austritt minus aktueller Sollwert. Positive Werte bedeuten: Austritt ist wärmer als der Sollwert.">Δ VL–Soll: {{ deltaText(supplyDelta) }} K</span>
                <button class="refresh-inline" type="button" :disabled="refreshing" @click="loadDashboard(false)">
                  <RefreshCw :size="15" :class="{ spinning: refreshing }" /> {{ refreshing ? 'Lese Werte …' : 'Jetzt aktualisieren' }}
                </button>
              </div>
            </div>
            <div v-if="readings.length" class="hero-metrics" :style="{'--overview-desktop': Math.min(metricColumns, readings.length), '--overview-tablet': Math.min(mobileProfile ? metricColumns : 6, metricColumns, readings.length), '--overview-mobile': Math.min(metricColumns, mobileProfile ? 4 : 3, readings.length), '--overview-narrow': Math.min(metricColumns, 2, readings.length)}">
              <div v-for="item in readings" :key="item.key" class="hero-metric"
                :class="['reading-'+item.key, { 'is-stale': item.stale }]"
                :title="readingHint(item.key)">
                <component :is="item.icon" :size="24" :stroke-width="1.8" />
                <strong :class="{'gira-text':item.compactText}">{{ item.text }} <small v-if="item.unit" class="metric-unit">{{ item.unit }}</small></strong>
                <span v-if="item.label" class="metric-label">{{ item.label }}</span>
                <template v-if="item.key === 'timer_m1'">
                  <small>{{ m1Status }}</small>
                  <small v-if="m1InWindow" title="Berechnet mit der Ortszeit des Browsers">Im Zeitfenster</small>
                </template>
                <small v-if="item.key==='flow'" class="pump-pwm" :class="{'is-stale':pumpPwm?.quality==='stale'}" :title="pumpPwm?'UP PWM aktuell · Register 2115 · Quelle: '+valueSource(2115)+' · '+relativeTimestamp(pumpPwm.timestamp):'Noch kein bestätigter Pumpen-PWM-Wert vorhanden'">UP {{ pumpPwm ? displayMetric(pumpPwm) : '—' }} %</small>
              </div>
            </div>
          </div>
        </section>

        <div class="below-hero">
          <p v-if="transportPaused" class="notice" role="status">Kommunikation pausiert. Angezeigt werden zuletzt bekannte Werte.</p>
          <p v-else-if="longValuePause" class="notice" role="status">Über die gewählte Verbindung sind seit über 30 Minuten keine neuen Werte eingetroffen.</p>
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
              <select id="home-transport" v-model="selectedTransport" :disabled="transportBusy || !adminAuthenticated">
                <option value="cloud">Cloud</option>
                <option value="standard_modbus">Modbus-Standard</option>
                <option value="warmlink_raw">Modbus-LTE</option>
                <option value="display_modbus">Modbus-Display</option>
              </select>
              <small class="bus-live-note">Gilt für alle Geräte{{ adminAuthenticated ? '' : ' · Änderung als Administrator' }}</small>
              <small v-if="transportError" class="error-text" role="alert">{{ transportError }}</small>
              <div class="live-inline" v-if="selectedTransport === 'cloud'">
                <label class="live-switch"><input type="checkbox" v-model="liveEnabled" /> Automatische Cloud-Abfrage</label>
                <small>{{ liveEnabled ? 'alle ' + liveInterval + ' s · nur bei sichtbarer Übersicht' : 'deaktiviert' }}</small>
              </div>
              <small v-if="selectedTransport==='standard_modbus'" role="status">{{ snapshot?.transport === selectedTransport && snapshot.error ? snapshot.error : 'Automatische Aktualisierung bei sichtbarer Übersicht' }}</small>
              <small v-if="isBusTransport" class="bus-live-note" role="status">{{ busConnectionNote }}</small>
            </div>
          </section>

          <div class="content-columns">
            <section class="shortcuts panel">
              <div class="section-head"><div><span class="section-caption">SCHNELLZUGRIFF</span><h2>Funktionen</h2></div><span class="muted-text">Parameter auswählen</span></div>
              <div class="shortcut-grid">
                <button class="shortcut" @click="historyOpen=true">
                  <span class="shortcut-symbol lilac"><Activity :size="28" /></span>
                  <strong>Verlauf &amp; Diagramme</strong><small>Historische Cloud-Messwerte</small><ChevronRight :size="16" class="shortcut-arrow" />
                </button>
                <button v-for="button in actionButtons" :key="button.label" class="shortcut" @click="openSpecialDialog(button.dialog)">
                  <span class="shortcut-symbol" :class="button.color"><component :is="button.icon" :size="28" /></span>
                  <strong>{{ button.label }}</strong>
                  <small>{{ button.hint }}</small>
                  <ChevronRight :size="16" class="shortcut-arrow" />
                </button>
              </div>
            </section>

            <section class="panel operating-panel">
              <div class="section-head"><div><span class="section-caption">BETRIEB</span><h2>Auf einen Blick</h2></div></div>
              <ExpertGira v-if="!glance.includes('gira')" v-show="false" @values="giraItems = $event" />
              <div class="glance-order">
                <template v-for="key in glanceOrder" :key="key">
                  <ExpertGira v-if="key === 'gira'" class="glance-wide" @values="giraItems = $event" />
                  <button v-else-if="key === 'power'" type="button" class="operation operation-button" :disabled="transportPaused" @click="operationDialog?.open('Power')"><span class="operation-icon"><Power :size="24" /></span><span>Ein / Aus</span><strong>{{ powerText }}</strong></button>
                  <button v-else-if="key === 'mode'" type="button" class="operation operation-button" :disabled="transportPaused" @click="operationDialog?.open('Mode')"><span class="operation-icon"><Sun :size="24" /></span><span>Modus</span><strong>{{ modeText }}</strong></button>
                  <button v-else-if="key === 'silent'" type="button" class="operation operation-button" :disabled="transportPaused" @click="operationDialog?.open('H22')"><span class="operation-icon"><VolumeX :size="24" /></span><span>Ruhemodus</span><strong>{{ metric('silent').replace('Silent-Modus ', '') }}</strong></button>
                  <button v-else-if="key === 'parameters'" type="button" class="main-action glance-wide" @click="navigate('parameters')"><SlidersHorizontal :size="19" /><span>Parameter & Einstellungen</span><ArrowRight :size="19" /></button>
                  <div v-else-if="key.startsWith('spacer:')" class="glance-spacer" aria-hidden="true"></div>
                  <div v-else-if="key === 'timer_m1'" class="power-summary">
                    <div :class="{'is-stale':m1Limit?.stale}">
                      <Gauge :size="17" aria-hidden="true" />
                      <strong>{{ m1Limit?.max_kw?.toLocaleString('de-DE', { maximumFractionDigits: 1 }) ?? '—' }} kW</strong>
                      <small>{{ overviewFields.timer_m1.label }}</small>
                      <small>{{ m1Status }}</small>
                      <small v-if="m1InWindow" title="Berechnet mit der Ortszeit des Browsers">Im Zeitfenster</small>
                    </div>
                  </div>
                  <PowerSummary v-else :metrics="snapshot?.metrics" :selection="[key]" :gira="giraItems" :spread="waterSpread" />
                </template>
              </div>
              <p class="section-hint">Neue Messwerte erscheinen automatisch. Schreibfunktionen hängen von Verbindung und Benutzerrechten ab.</p>
            </section>
          </div>
          <MainRegisterBrowser :rows="browserRows" :transport="selectedTransport" @parameters="navigate('parameters')" />
        </div>
      </template>

      <template v-else-if="page === 'parameters'">
        <section class="page-heading"><div><span class="section-caption">FOX AIR / TECHNIK</span><h1>Parameter & Einstellungen</h1><p>Register aus dem gemeinsamen FoxAir_Control-Katalog.</p></div><button class="back-link" @click="navigate('home')"><ArrowLeft :size="17" /> Übersicht</button></section>
        <div class="work-layout">
          <section class="panel register-list">
            <ParameterFilters v-model:search="search" v-model:group="selectedGroup" :groups="orderedGroups" :show-groups="!cloudView" :favorites-only="favoritesOnly" :favorite-count="favoriteIds.length" @toggle-favorites="toggleFavoriteFilter">
            <div class="source-tabs" role="group" aria-label="Register- oder Cloudansicht">
              <button type="button" :class="{ active: !cloudView }" @click="cloudView = false">Modbus-Register</button>
              <button type="button" :class="{ active: cloudView }" @click="cloudView = true">Alle Cloud-Codes <small>{{ cloudOverview?.total ?? 0 }}</small></button>
            </div>
            </ParameterFilters>
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
            <div v-if="!cloudView" class="register-toolbar"><span>{{ registerLoading ? 'Suche …' : registers.length + ' Treffer · ' + catalogSize + ' Register gesamt' }}</span><span>{{ transportLabel }}</span></div>
            <div v-if="!cloudView && selectedTransport==='display_modbus'" class="lte-summary">
              <div class="lte-summary-info"><strong>Display · {{lteScan.completed}}/{{lteScan.total}} Parameterpakete</strong><span>{{busState?.connected?'Bus verbunden':'Bus nicht verbunden'}} · {{Object.keys(localValues).length}} Werte · passiver Empfang</span></div>
              <button class="outlined-action" :disabled="!adminAuthenticated || scanStarting || lteScan.status==='running' || !busState?.connected" @click="startLteScan">Alle Werte vom Bus lesen</button>
              <p v-if="lteScan.error" role="alert" class="read-error">{{lteScan.error}}</p>
            </div>
            <LteScanSummary v-if="!cloudView&&selectedTransport==='warmlink_raw'" :scan="lteScan" :value-count="Object.keys(localValues).length" :connected="pushConnected" :starting="scanStarting" @refresh="startLteScan" />
            <p v-if="!cloudView&&catalogError" role="alert" class="read-error">{{ catalogError }}</p>
            <div v-if="!cloudView" class="register-items">
              <button v-for="entry in registers" :key="entry.register" class="register-item" :class="{ active: selectedRegister?.register === entry.register }" @click="selectRegister(entry)">
                <span class="register-code">{{ entry.code || entry.register }}</span>
                <span class="register-title">{{ entry.name }}<small>{{ entry.register }}</small></span>
                <span class="register-measure" :class="{ unknown: currentRegisterValue(entry.register)?.value == null,
                    'is-stale': currentRegisterValue(entry.register)?.quality === 'stale' }"
                  :title="relativeTimestamp(currentRegisterValue(entry.register)?.timestamp)">
                  {{ currentRegisterValue(entry.register)?.display_value ?? entry.cloud?.display_value ?? textValue(currentRegisterValue(entry.register)?.value ?? entry.cloud?.value) }}
                  <small>{{ currentRegisterValue(entry.register)?.unit ?? entry.cloud?.unit ?? '' }}</small>
                  <small v-if="currentRegisterValue(entry.register)?.quality === 'stale'">veraltet</small>
                </span>
                <ChevronRight :size="16" />
              </button>
              <p v-if="!registerLoading && !registers.length" class="empty-state">Keine passenden Register gefunden.</p>
            </div>
            <div v-else class="register-items">
              <button v-for="entry in filteredCloudRows" :key="entry.code" class="register-item"
                :class="{ active: cloudCodeSelected?.code === entry.code }" @click="selectCloudParameter(entry)">
                <span class="register-code">{{ entry.code }}</span>
                <span class="register-title">{{ entry.name }}
                  <small>{{ entry.register ? 'Register ' + entry.register : 'Nur Cloud' }} · {{ entry.kind }}</small></span>
                <span class="register-measure" :class="{ unknown: entry.value == null, 'is-stale': entry.quality === 'stale' }" :title="relativeTimestamp(entry.timestamp)">
                  {{ entry.display_value ?? textValue(entry.value) }} <small>{{ entry.unit }}</small>
                  <small v-if="entry.quality === 'stale'">veraltet</small>
                </span>
                <ChevronRight :size="16" />
              </button>
              <p v-if="!filteredCloudRows.length" class="empty-state">Keine passenden Cloud-Codes.</p>
            </div>
          </section>
          <ParameterDetails ref="parameterDetails">
            <template v-if="cloudView && cloudCodeSelected">
              <span class="section-caption">CLOUD-CODE</span>
              <h2>{{ cloudCodeSelected.name }}</h2>
              <span class="register-code large">{{ cloudCodeSelected.code }}</span>
              <ParameterValue label="Cloud-Wert" :value="cloudCodeSelected.display_value ?? cloudCodeSelected.value" :unit="cloudCodeSelected.unit" :timestamp="cloudCodeSelected.timestamp" :quality="cloudCodeSelected.quality" />
              <div class="detail-metadata">
                <span>Modbus-Zuordnung <strong>{{ cloudCodeSelected.register ?? 'nicht bestätigt' }}</strong></span>
                <span>Cloud-Kategorie <strong>{{ cloudCodeSelected.kind }}</strong></span>
                <span>Mapping-Confidence <strong>{{ cloudCodeSelected.confidence || 'unbekannt' }}</strong></span>
                <span>Quelle <strong>Cloud</strong></span><span>Unterstützung <strong>{{ cloudCodeSelected.supported ? 'Wert vorhanden' : 'kein Wert' }}</strong></span>
              </div>
              <p v-if="cloudCodeSelected.description" class="description parameter-description">{{ cloudCodeSelected.description }}</p>
              <p class="section-hint">Cloud-Originalwert in API-Skalierung; keine Umrechnung anhand lokaler Modbus-Rohwerte.</p>
            </template>
            <template v-else-if="!cloudView && selectedRegister">
              <span class="section-caption">PARAMETERDETAILS</span>
              <div class="detail-top"><div><span class="register-code large">{{ selectedRegister.code || selectedRegister.register }}</span><h2>{{ selectedRegister.name }}</h2></div><button type="button" class="favorite-button" :class="{selected:isFavorite(selectedRegister.register)}" :aria-pressed="isFavorite(selectedRegister.register)" :aria-label="isFavorite(selectedRegister.register)?'Favorit entfernen':'Als Favorit merken'" @click="toggleFavorite(selectedRegister.register)"><Star :size="23" :fill="isFavorite(selectedRegister.register)?'currentColor':'none'" /></button></div>
              <ParameterValue :value="currentRegisterValue(selectedRegister.register)?.display_value ?? selectedRegister.cloud?.display_value ?? currentRegisterValue(selectedRegister.register)?.value ?? selectedRegister.cloud?.value" :unit="currentRegisterValue(selectedRegister.register)?.unit ?? selectedRegister.cloud?.unit ?? ''" :timestamp="currentRegisterValue(selectedRegister.register)?.timestamp ?? selectedRegister.cloud?.timestamp" :quality="currentRegisterValue(selectedRegister.register)?.quality" />
              <div class="detail-metadata"><span>Modbus-Register <strong>{{ selectedRegister.register }}</strong></span><span>Gruppe <strong>{{ selectedRegister.group }}</strong></span><span>Typ <strong>{{ selectedRegister.type }}</strong></span><span>Zugriff <strong>{{ selectedRegister.mode }}</strong></span><span>Quelle <strong>{{ valueSource(selectedRegister.register) }}</strong></span></div>
              <h3 class="parameter-description-title">Beschreibung & Hinweise</h3>
              <p class="description parameter-description">{{ selectedRegister.description || 'Keine zusätzliche Beschreibung vorhanden.' }}</p>
              <p v-if="readError" class="read-error">{{ readError }}</p>
              <button class="main-action" :disabled="reading || !selectedTransportInfo?.read_supported" @click="readRegister"><RefreshCw :size="18" :class="{ spinning: reading }" />{{ reading ? 'Wert wird gelesen …' : 'Register jetzt lesen' }}</button>
              <ParameterEditor v-if="selectedTransport!=='display_modbus'" :key="selectedTransport+':'+selectedRegister.register" :register="selectedRegister" :transport="selectedTransport" :admin="canOperate && browserOnline" :value="currentRegisterValue(selectedRegister.register)" @updated="readRegister" @read="currentValue=$event" />
            </template>
            <div v-else class="empty-detail"><SlidersHorizontal :size="35" /><h2>{{ cloudView ? 'Cloud-Code auswählen' : 'Parameter auswählen' }}</h2><p>Vorhandene Werte sind in der Liste sichtbar. Für Details einen Eintrag öffnen.</p></div>
          </ParameterDetails>
        </div>
      </template>

      <template v-else>
        <section class="page-heading"><div><span class="section-caption">ANWENDUNG</span><h1>App-Einstellungen</h1><p>Verbindungen, Anzeigen und Verwaltung.</p></div><button class="back-link" @click="navigate('home')"><ArrowLeft :size="17" /> Übersicht</button></section>
        <section v-if="sessionChecked && !adminAuthenticated" class="settings-panel settings-note settings-auth">
          <ShieldCheck :size="18" aria-hidden="true" />
          <div>
            <p v-if="!signedIn"><strong>Du bist nicht angemeldet.</strong> Melde dich als Administrator an, um alle Einstellungen zu sehen und zu ändern.</p>
            <p v-else>Du bist angemeldet. Für Webzugriff, Experteneinstellungen und weitere Verwaltungsfunktionen brauchst du Administratorrechte.</p>
            <button v-if="!signedIn" type="button" class="outlined-action" @click="loginOpen = true">Anmelden</button>
          </div>
        </section>
        <AccountManagement v-if="adminAuthenticated" />
        <OverviewSettings v-if="adminAuthenticated" :layout="overviewLayout" :gira-revision="giraRevision" @saved="overviewLayout = $event" />
        <LocalHistory v-if="adminAuthenticated" settings />
        <section class="settings-panel panel">
          <div class="section-head"><div><span class="section-caption">VERBINDUNG</span><h2>Transport auswählen</h2><button class="outlined-action" :aria-expanded="connectionSettingsOpen" @click="connectionSettingsOpen = !connectionSettingsOpen">Verbindungseinstellungen</button></div><ShieldCheck :size="24" /></div>
          <p>Die ausgewählte Verbindung gilt für alle Geräte und wird automatisch synchronisiert. Unter Verbindungseinstellungen richtest du Cloud und lokale Busanschlüsse ein.</p>
          <div class="transport-options">
            <label v-for="option in (transports.length ? transports : [
              { id: 'cloud', name: 'Cloud', configured: false, read_supported: false, reason: '' },
              { id: 'standard_modbus', name: 'Modbus-Standard', configured: false, read_supported: false, reason: '' },
              { id: 'warmlink_raw', name: 'Modbus-LTE', configured: false, read_supported: false, reason: '' },
              { id: 'display_modbus', name: 'Modbus-Display', configured: false, read_supported: false, reason: '' }
            ])" :key="option.id" class="transport-option" :class="{ active: selectedTransport === option.id }">
              <input v-model="selectedTransport" type="radio" name="transport" :value="option.id" :disabled="transportBusy || !adminAuthenticated" />
              <span class="transport-option-icon"><Cloud v-if="option.id === 'cloud'" :size="21" /><Wifi v-else-if="option.id === 'standard_modbus'" :size="21" /><Gauge v-else-if="option.id === 'display_modbus'" :size="21" /><RadioTower v-else :size="21" /></span>
              <span class="transport-option-text"><strong>{{ option.name }}</strong><small>{{ option.read_supported ? 'Lesen verfügbar' : option.reason || 'Noch nicht konfiguriert' }}</small></span>
              <span class="choice-mark"></span>
            </label>
          </div>
          <div class="settings-note"><Activity :size="18" /><p>Cloud und Modbus-Standard werden bei sichtbarer Übersicht aktualisiert. Display und LTE empfangen neue Buswerte live. Neue lokale Anschlüsse bleiben bis zur Einrichtung deaktiviert.</p></div>
          <button v-if="adminAuthenticated" type="button" class="outlined-action" :disabled="transportBusy" @click="setTransportPaused(!transportPaused)">{{ transportPaused ? 'Kommunikation fortsetzen' : 'Kommunikation pausieren' }}</button>
          <p v-if="transportError" class="read-error" role="alert">{{ transportError }}</p>
          <p v-if="transportPaused" class="section-hint">Abfragen und Schreibzugriffe sind pausiert. Die gewählte Verbindung bleibt gespeichert.</p>
          <button class="outlined-action" :disabled="transportPaused" @click="loadDashboard(false)"><RefreshCw :size="17" /> Verbindung erneut prüfen</button>
        </section>


        <section class="settings-panel panel">
          <div class="section-head"><div><span class="section-caption">LIVEABFRAGE</span><h2>Cloud-Aktualisierung</h2></div><RefreshCw :size="22" /></div>
          <label class="settings-check"><input type="checkbox" v-model="liveEnabled" /> Automatisch aktualisieren, solange die Übersicht sichtbar ist</label>
          <label class="field-label" for="live-interval">Intervall (10–3600 Sekunden)</label>
          <input id="live-interval" class="settings-input" type="number" min="10" max="3600" v-model.number="liveInterval" @change="liveInterval = Math.max(10, Math.min(3600, Number(liveInterval) || 30))" />
          <p class="section-hint">Livepoll mit app_heartbeat=23205 und nachfolgendem Datenabruf. Kein regelmäßiges Polling in inaktiven Tabs.</p>
        </section>

        <CloudInsights mode="device" :admin="adminAuthenticated&&secureAdminContext&&browserOnline" />
        <UpdatePanel :admin="adminAuthenticated && browserOnline" :secure="secureAdminContext"
          :version="installedVersion" :update-info="updateStatus" :update-loading="updateLoading"
          :check-error="updateCheckError" :checked-at="updateCheckedAt" @refresh="refreshUpdateStatus()" />
        <section class="settings-panel panel">
          <div class="section-head">
            <div><span class="section-caption">DIAGNOSE</span><h2>Verbindungsprotokoll</h2></div>
            <button type="button" class="outlined-action" @click="loadCloudLogs"><RefreshCw :size="16" /> Aktualisieren</button>
          </div>
          <p class="section-hint">Ereignisse für Cloud und lokale Busse: Verbindungen, Leseabfragen, LTE-Telegramme und Fehler. Ohne Zugangsdaten oder Tokens. Das Protokoll wird beim Dienstneustart zurückgesetzt.</p>
          <div class="cloud-log-list">
            <div v-for="(entry, index) in cloudLogs" :key="index" class="cloud-log-item">
              <time>{{ new Date(entry.time).toLocaleString('de-DE') }}</time>
              <span class="cloud-log-kind" :class="entry.kind">{{ entry.kind }}</span>
              <span>{{ entry.message }} <template v-if="entry.count !== undefined">({{ entry.count }})</template></span>
            </div>
            <p v-if="!cloudLogs.length" class="empty-state">Noch keine Cloud-Ereignisse aufgezeichnet.</p>
          </div>
        </section>
        <LanAccessSettings v-if="adminAuthenticated && browserOnline" />
        <details v-if="adminAuthenticated" class="settings-panel panel expert-settings">
          <summary>Experteneinstellungen</summary>
          <ExpertCamera v-if="secureAdminContext && browserOnline" @saved="cameraConfig = $event" />
          <ExpertGira settings :admin="adminAuthenticated" :secure="secureAdminContext" @saved="giraRevision++" />
        </details>
      </template>
    </main>


    <CameraDialog ref="cameraDialog" :available="canOpenCamera && page === 'home'"
      :mode="cameraConfig?.mode" :interval="cameraConfig?.interval_ms ?? 2000" />
    <dialog ref="historyDialogElement" class="connection-dialog panel" aria-labelledby="history-dialog-title" @close="historyOpen=false" @cancel="historyOpen=false">
      <div class="connection-dialog-content">
        <header class="connection-dialog-header"><div><span class="section-caption">VERLAUF</span><h2 id="history-dialog-title">Verlauf &amp; Diagramme</h2></div><button class="outlined-action" aria-label="Verlauf schließen" @click="historyOpen=false">Schließen</button></header>
        <LocalHistory v-if="historyOpen" />
        <CloudInsights v-if="historyOpen" mode="history" :admin="adminAuthenticated&&secureAdminContext&&browserOnline" />
      </div>
    </dialog>
    <ConnectionSettingsDialog v-model="connectionSettingsOpen" v-model:admin-password="cloudAdminPassword"
      :admin="adminAuthenticated" :secure="secureAdminContext" :admin-busy="adminBusy" :admin-login-error="adminLoginError"
      :bus-state="busState" :cloud-overview="cloudOverview" @login="loginAsAdmin" @logout="logoutAsAdmin"
      @connections-changed="reloadTransportOptions" @refresh-cloud="loadCloudValues" />

    <TargetEditorDialog ref="targetEditor" :can-edit="canEditTarget" :transport="selectedTransport"
      :effective-target="snapshot?.metrics.target?.source_code === '2014' ? metric('target') + ' °C' : '—'"
      :current-value="currentRegisterValue(1158)" @updated="loadDashboard(false)" />
    <OperationDialog ref="operationDialog" :transport="selectedTransport" :transport-label="transportLabel"
      :admin="adminAuthenticated" :can-operate="adminAuthenticated && secureAdminContext && browserOnline && !transportPaused"
      :cloud-rows="cloudRows" :cached-value="currentRegisterValue" @updated="page === 'home' && loadDashboard(false)" @refresh-cloud="loadCloudValues" />

    <dialog ref="specialDialogElement" class="special-modal panel native-special" aria-labelledby="special-modal-title" @close="specialDialog=null" @cancel="specialDialog=null" @click.self="specialDialog=null">
      <div v-if="specialDialog" class="special-dialog-content">
        <div class="special-top">
          <div><span class="section-caption">FOX AIR / {{ transportLabel }}</span>
            <h2 id="special-modal-title">{{ selectedSpecial?.title || 'Spezialdialog' }}</h2>
            <p>{{ selectedSpecial?.description }}</p></div>
          <button type="button" class="outlined-action" aria-label="Dialog schließen" @click="specialDialog = null">Schließen</button>
        </div>
        <TimerEditor v-if="specialDialog==='timer'||specialDialog==='silent'" :key="specialDialog" :transport="selectedTransport" :admin="adminAuthenticated&&secureAdminContext&&browserOnline" :silent="specialDialog==='silent'" />
        <template v-else>
        <p class="section-hint">Werte aus der ausgewählten Verbindung wie in FoxAir_Control. Bekannte Einstellungen sind für Administratoren bearbeitbar. Jeder Wert wird vor dem Schreiben geprüft und danach zurückgelesen. Störungswerte bleiben lesend.</p>
        <div class="special-toolbar">
          <button type="button" class="outlined-action" :disabled="specialLoading || transportPaused" @click="refreshSelectedSpecial">
            <RefreshCw :size="16" :class="{ spinning: specialLoading }" />
            {{ specialLoading ? 'Werte werden gelesen …' : 'Werte aktualisieren' }}
          </button>
          <span v-if="selectedTransport === 'cloud'">{{ specialRows.filter(row => row.value !== null).length }} / {{ specialRows.length }} mit Wert</span>
        </div>
        <p v-if="specialMessage" role="status" class="success-text">{{ specialMessage }}</p>
        <p v-if="specialError" role="alert" class="read-error">{{ specialError }}</p>
        <RegisterDecoder v-if="specialDialog === 'decoder'" :transport="selectedTransport" :value-for="currentRegisterValue" :cloud-rows="cloudRows" />
        <SpecialControls v-if="selectedSpecial && (['at','sg','wp'].includes(selectedSpecial.id) || selectedSpecial.id === 'fault' && selectedTransport !== 'cloud')" :key="selectedTransport+':'+selectedSpecial.id" :dialog="selectedSpecial" :transport="selectedTransport" :admin="adminAuthenticated && secureAdminContext && browserOnline" :value-for="currentRegisterValue" @updated="refreshSelectedSpecial" />
        <div v-if="!selectedSpecial || selectedSpecial.id === 'fault' && selectedTransport === 'cloud'" class="special-rows">
          <div v-for="entry in specialRows" :key="entry.code" class="main-register-row"
            :class="{ 'is-stale': entry.quality === 'stale' }">
            <span class="register-code">{{ entry.register ?? entry.code }}</span>
            <span class="register-title">{{ entry.name }}
              <small>{{ entry.register != null ? 'Register ' + entry.register : 'Nur Cloud' }}</small>
            </span>
            <strong :title="relativeTimestamp(entry.timestamp)">{{ textValue(entry.value) }} {{ entry.unit }}</strong>
          </div>
          <p v-if="!specialRows.length" class="empty-state">Noch keine Werte aus dieser Verbindung vorhanden.</p>
        </div>
        </template>
      </div>
    </dialog>

    <nav class="mobile-bottom" aria-label="Mobilnavigation">
      <button :class="{ active: page === 'home' }" @click="navigate('home')"><House :size="21" /><span>Übersicht</span></button>
      <button :class="{ active: page === 'parameters' }" @click="navigate('parameters')"><SlidersHorizontal :size="21" /><span>Parameter</span></button>
      <button :class="{ active: page === 'settings' }" @click="navigate('settings')"><Settings2 :size="21" /><span>Mehr</span></button>
    </nav>
  </div>
</template>
