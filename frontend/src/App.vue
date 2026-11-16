<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Activity, ArrowDownLeft, ArrowLeft, ArrowRight, ArrowUpRight, Bell,
  ChevronRight, Clock3, Cloud, Fan, Gauge, HeartPulse, House,
  Menu, Minus, Plus, Power, RadioTower, RefreshCw, Search,
  Settings2, ShieldCheck, SlidersHorizontal, Snowflake, Star,
  Sun, Thermometer, VolumeX, Waves, Wifi, X, Zap
} from 'lucide-vue-next'
import { api } from './api'
import type { Dashboard, Metric, Register, RegisterValue, Transport, TransportId } from './api'

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
const lastUpdated = computed(() => {
  if (!snapshot.value?.timestamp || snapshot.value?.status === 'unavailable') return 'Noch keine aktuellen Messwerte'
  return 'Abfrage ' + new Date(snapshot.value.timestamp).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})
const actionButtons = [
  { label: 'Timer', hint: 'Zeitprogramme', icon: Clock3, color: 'apricot', search: 'Timer' },
  { label: 'SG-Ready', hint: 'PV-Steuerung', icon: Zap, color: 'mint', search: 'SG' },
  { label: 'Ruhemodus', hint: 'Leise Betriebsart', icon: VolumeX, color: 'lilac', search: 'Silent' },
]
const readings = computed(() => [
  { key: 'flow', label: 'Durchfluss', icon: Waves, unit: 'm³/h' },
  { key: 'tank', label: 'Warmwasser', icon: Thermometer, unit: '°C' },
  { key: 'outdoor', label: 'Außen', icon: Sun, unit: '°C' },
  { key: 'return', label: 'Rücklauf', icon: ArrowDownLeft, unit: '°C' },
  { key: 'supply', label: 'Vorlauf', icon: ArrowUpRight, unit: '°C' },
] as const))

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
function syncRoute() { page.value = routeFromHash() }
function navigate(target: Page, term = '') {
  if (target === 'parameters' && term) search.value = term
  window.location.hash = target === 'home' ? '#/' : '#/' + target
  syncRoute()
  if (target === 'parameters') void loadRegisters()
}
async function loadDashboard() {
  refreshing.value = true
  error.value = ''
  snapshot.value = null
  try {
    snapshot.value = await api.dashboard(selectedTransport.value)
    if (snapshot.value.error) error.value = snapshot.value.error
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Keine Verbindung zum Webserver'
  } finally {
    refreshing.value = false
  }
}
async function loadRegisters() {
  registerLoading.value = true
  try {
    const result = await api.registers(search.value)
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
  void loadDashboard()
})
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { if (page.value === 'parameters') void loadRegisters() }, 240)
})
onMounted(async () => {
  syncRoute()
  window.addEventListener('hashchange', syncRoute)
  try {
    const response = await api.transports()
    transports.value = response.items
  } catch {
    // Backend not reachable; show unavailable values, never demo values.
  }
  await loadDashboard()
  if (page.value === 'parameters') await loadRegisters()
})
onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncRoute)
  clearTimeout(searchTimer)
})
</script>

<template>
  <div class="app-shell">
    <header class="shell-header">
      <button class="brand" type="button" @click="navigate('home')" aria-label="Zur Übersicht">
        <span class="brand-mark"><Fan :size="20" stroke-width="2.5" /></span>
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
                  <div class="fan-ring"><Fan :size="94" :stroke-width="1.3" /></div>
                  <span class="unit-brand">FOX<span>AIR</span></span>
                </div>
                <span class="unit-ground"></span>
              </div>
              <div class="target-temperature">
                <span class="overline">Heizungs-Solltemperatur</span>
                <div class="temp-adjust">
                  <button class="round-adjust" type="button" disabled title="Sollwertschreiben folgt in einer späteren Version" aria-label="Solltemperatur senken"><Minus :size="25" /></button>
                  <strong>{{ metric('target') }}<small v-if="snapshot?.metrics.target"> °C</small></strong>
                  <button class="round-adjust" type="button" disabled title="Sollwertschreiben folgt in einer späteren Version" aria-label="Solltemperatur erhöhen"><Plus :size="25" /></button>
                </div>
                <span class="hero-footnote">{{ modeText === '—' ? 'Zieltemperatur · noch kein Messwert' : 'Aktueller Modus: ' + modeText }}</span>
                <button class="refresh-inline" type="button" :disabled="refreshing" @click="loadDashboard">
                  <RefreshCw :size="15" :class="{ spinning: refreshing }" /> {{ refreshing ? 'Lese Werte …' : 'Jetzt aktualisieren' }}
                </button>
              </div>
            </div>
            <div class="hero-metrics">
              <div v-for="item in readings" :key="item.key" class="hero-metric">
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
              <div><span class="section-caption">ANLAGENSTATUS</span><h2>{{ powerText === '—' ? 'Status nicht verfügbar' : powerText === 'Ein' ? 'Anlage eingeschaltet' : powerText === 'Aus' ? 'Anlage ausgeschaltet' : 'Betrieb: ' + powerText }}</h2><p>{{ lastUpdated }}</p></div>
            </div>
            <div class="transport-inline">
              <label for="home-transport">Verbindung</label>
              <select id="home-transport" v-model="selectedTransport">
                <option value="cloud">PHNIX-Cloud</option>
                <option value="standard_modbus">Standard-Modbus</option>
                <option value="display_modbus">Display-Modbus</option>
                <option value="warmlink_raw">LTE-/Warmlink-Modbus</option>
              </select>
            </div>
          </section>

          <div class="content-columns">
            <section class="shortcuts panel">
              <div class="section-head"><div><span class="section-caption">SCHNELLZUGRIFF</span><h2>Funktionen</h2></div><span class="muted-text">Parameter auswählen</span></div>
              <div class="shortcut-grid">
                <button v-for="button in actionButtons" :key="button.label" class="shortcut" @click="navigate('parameters', button.search)">
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
              <p class="section-hint">Schreibfunktionen und kontinuierlicher Live-Modus werden nach der sicheren Anbindung ergänzt.</p>
            </section>
          </div>
        </div>
      </template>

      <template v-else-if="page === 'parameters'">
        <section class="page-heading"><div><span class="section-caption">FOX AIR / TECHNIK</span><h1>Parameter & Einstellungen</h1><p>Register aus dem gemeinsamen FoxAir_Control-Katalog.</p></div><button class="back-link" @click="navigate('home')"><ArrowLeft :size="17" /> Übersicht</button></section>
        <div class="work-layout">
          <section class="panel register-list">
            <label class="search-box"><Search :size="19" /><input v-model="search" placeholder="Code, Name oder Register suchen" aria-label="Parameter suchen" /></label>
            <div class="register-toolbar"><span>{{ registerLoading ? 'Suche …' : registers.length + ' von ' + catalogSize + ' Registern' }}</span><span>{{ transportLabel }}</span></div>
            <div class="register-items">
              <button v-for="entry in registers" :key="entry.register" class="register-item" :class="{ active: selectedRegister?.register === entry.register }" @click="selectRegister(entry)">
                <span class="register-code">{{ entry.code || entry.register }}</span>
                <span class="register-title">{{ entry.name }}<small>Register {{ entry.register }}</small></span>
                <ChevronRight :size="16" />
              </button>
              <p v-if="!registerLoading && !registers.length" class="empty-state">Keine passenden Register gefunden.</p>
            </div>
          </section>
          <section class="panel register-detail">
            <template v-if="selectedRegister">
              <span class="section-caption">PARAMETERDETAILS</span>
              <div class="detail-top"><div><span class="register-code large">{{ selectedRegister.code || 'MAIN' }}</span><h2>{{ selectedRegister.name }}</h2></div><Star :size="23" class="star-muted" /></div>
              <div class="detail-value"><span>Aktueller Wert</span><strong>{{ currentValue ? displayMetric({ value: currentValue.value, unit: currentValue.unit, raw: currentValue.raw, timestamp: currentValue.timestamp, quality: currentValue.quality }) : '—' }} <small>{{ currentValue?.unit || '' }}</small></strong><p>{{ currentValue ? 'Ausgelesen: ' + new Date(currentValue.timestamp).toLocaleString('de-DE') : 'Noch nicht ausgelesen' }}</p></div>
              <div class="detail-metadata"><span>Modbus-Register <strong>{{ selectedRegister.register }}</strong></span><span>Typ <strong>{{ selectedRegister.type }}</strong></span><span>Zugriff <strong>{{ selectedRegister.mode }}</strong></span></div>
              <p class="description">{{ selectedRegister.description || 'Keine zusätzliche Beschreibung vorhanden.' }}</p>
              <p v-if="readError" class="read-error">{{ readError }}</p>
              <button class="main-action" :disabled="reading || !selectedTransportInfo?.read_supported" @click="readRegister"><RefreshCw :size="18" :class="{ spinning: reading }" />{{ reading ? 'Wert wird gelesen …' : 'Register jetzt lesen' }}</button>
              <p class="section-hint">Schreiben ist in diesem ersten Entwicklungsstand deaktiviert. {{ selectedTransportInfo?.read_supported ? '' : selectedTransportInfo?.reason || '' }}</p>
            </template>
            <div v-else class="empty-detail"><SlidersHorizontal :size="35" /><h2>Parameter auswählen</h2><p>Links nach D14, E17, 1158 oder einer Beschreibung suchen und den Registereintrag öffnen.</p></div>
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
          <div class="settings-note"><Activity :size="18" /><p>Standard-Modbus arbeitet derzeit nur bei Anforderung: TCP verbinden, lesen und direkt wieder schließen. Ein dauerhafter Live-Modus folgt mit dem Lease-Manager. Display/LTE bleiben bis zur Busarbitrierungsprüfung passiv.</p></div>
          <button class="outlined-action" @click="loadDashboard"><RefreshCw :size="17" /> Verbindung erneut prüfen</button>
        </section>
      </template>
    </main>

    <nav class="mobile-bottom" aria-label="Mobilnavigation">
      <button :class="{ active: page === 'home' }" @click="navigate('home')"><House :size="21" /><span>Übersicht</span></button>
      <button :class="{ active: page === 'parameters' }" @click="navigate('parameters')"><SlidersHorizontal :size="21" /><span>Parameter</span></button>
      <button :class="{ active: page === 'settings' }" @click="navigate('settings')"><Settings2 :size="21" /><span>Mehr</span></button>
    </nav>
  </div>
</template>
