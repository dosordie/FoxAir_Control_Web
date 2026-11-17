<script setup lang="ts">
import { nextTick, ref, toRef, watch } from 'vue'
import { Cloud, Search, RefreshCw } from 'lucide-vue-next'
import type { CloudValues, ConnectionState, TransportId } from '../api'
import { useConnectionSettings } from '../composables/useConnectionSettings'
const props = defineProps<{
  admin: boolean
  secure: boolean
  adminBusy: boolean
  adminLoginError: string
  busState: ConnectionState | null
  cloudOverview: CloudValues | null
}>()
const connectionSettingsOpen = defineModel<boolean>({ required: true })
const cloudAdminPassword = defineModel<string>('adminPassword', { required: true })
const emit = defineEmits<{
  login: []
  logout: []
  connectionsChanged: [transport: TransportId]
  refreshCloud: []
}>()
const connectionDialogElement = ref<HTMLDialogElement | null>(null)
watch(connectionSettingsOpen, async (opened) => {
  await nextTick()
  const dialog = connectionDialogElement.value
  if (opened && dialog && !dialog.open) dialog.showModal()
  else if (!opened && dialog?.open) dialog.close()
})
const {
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
} = useConnectionSettings(
  toRef(props, 'admin'),
  toRef(props, 'secure'),
  (transport) => emit('connectionsChanged', transport),
  () => emit('refreshCloud'),
)
</script>
<template>
  <dialog
    ref="connectionDialogElement"
    class="connection-dialog panel"
    aria-labelledby="connection-dialog-title"
    @close="connectionSettingsOpen = false"
    @cancel="connectionSettingsOpen = false"
    @click.self="connectionSettingsOpen = false"
  >
    <div class="connection-dialog-content">
      <header class="connection-dialog-header">
        <div>
          <span class="section-caption">VERBINDUNG</span>
          <h2 id="connection-dialog-title">Verbindungseinstellungen</h2>
        </div>
        <button
          class="outlined-action"
          type="button"
          aria-label="Verbindungseinstellungen schließen"
          @click="connectionSettingsOpen = false"
        >
          Schließen
        </button>
      </header>
      <p class="section-hint">
        Cloud-Zugang und lokaler LTE-Anschluss. Die aktive Verbindung wählst du auf der
        Einstellungsseite.
      </p>
      <section class="connection-section">
        <div class="section-heading">
          <div>
            <span class="section-caption">LTE / WARMLINK</span>
            <h2>Lokaler LTE-Bus</h2>
          </div>
        </div>
        <p class="section-hint">
          Raw-TCP-/ser2net-Anschluss, 9600 8N1, Slave 99. Vorhandener DTU-Verkehr wird
          berücksichtigt. Bei konkurrierenden Abfragen wird abgebrochen.
        </p>
        <p v-if="!admin" class="section-hint">Zum Konfigurieren oben rechts anmelden.</p>
        <form v-else @submit.prevent="saveLteConfig" class="cloud-form">
          <label class="field-label" for="lte-host">IP-Adresse</label>
          <input id="lte-host" class="settings-input" v-model="lteConfig.host" required />
          <label class="field-label" for="lte-port">TCP-Port</label>
          <input
            id="lte-port"
            class="settings-input"
            type="number"
            min="1"
            max="65535"
            v-model.number="lteConfig.port"
            required
          />
          <label class="field-label" for="connection-mode">Verbindung offen halten</label>
          <select id="connection-mode" class="settings-input" v-model="lteConfig.connection_mode">
            <option value="on_demand">Nur bei einer Abfrage</option>
            <option value="browser">Solange ein Browser geöffnet ist</option>
            <option value="permanent">Dauerhaft – auch ohne Browser</option>
          </select>
          <p class="section-hint">
            Browser-Modus: Schließen spätestens 90 Sekunden nach dem letzten Lebenszeichen.
            Dauerhaftes Mithören sendet keine eigenen Lese- oder Schreibbefehle.
          </p>
          <p role="status">
            TCP: {{ busState?.connected ? 'Verbunden' : 'Geschlossen' }} · Modus:
            {{
              { on_demand: 'Bei Bedarf', browser: 'Browser geöffnet', permanent: 'Dauerhaft' }[
                busState?.mode as 'on_demand' | 'browser' | 'permanent'
              ] || 'Bei Bedarf'
            }}<span v-if="busState?.error"> · {{ busState.error }}</span>
          </p>
          <label
            ><input type="checkbox" v-model="lteConfig.enabled" /> LTE-Verbindung mit Lesen und
            freigegebenen Schreibfunktionen aktivieren</label
          >
          <button class="main-action" :disabled="lteBusy">
            {{ lteBusy ? 'Speichert …' : 'LTE-Anschluss speichern' }}
          </button>
        </form>
        <p v-if="lteMessage" class="section-hint" role="status">{{ lteMessage }}</p>
        <p v-if="lteError" class="read-error" role="alert">{{ lteError }}</p>
      </section>
      <section class="connection-section cloud-panel">
        <div class="section-head">
          <div>
            <span class="section-caption">PHNIX / WARMLINK</span>
            <h2>Cloud-Zugang & Geräte</h2>
          </div>
          <Cloud :size="24" />
        </div>
        <p>
          Cloud:
          <strong>{{ cloudStatus?.configured ? 'eingerichtet' : 'nicht vollständig' }}</strong> ·
          Benutzer {{ cloudStatus?.username_configured ? 'vorhanden' : 'fehlt' }} · Gerätekennung
          {{ cloudStatus?.device_configured ? 'vorhanden' : 'fehlt' }}
        </p>
        <p v-if="!cloudStatus?.admin_enabled" class="read-error">
          Web-Administration lokal einrichten: <code>python3 scripts/setup_web_admin.py</code>
        </p>
        <p v-else-if="!secure" class="read-error">
          Für die Cloud-Bearbeitung HTTPS oder einen lokalen SSH-Tunnel verwenden. Über
          unverschlüsseltes LAN-HTTP bleibt sie gesperrt.
        </p>
        <div class="admin-session">
          <p>
            <strong>Zugriff: {{ admin ? 'Administrator' : 'Lesender Gast' }}</strong> — Werte sind
            ohne Anmeldung sichtbar.
          </p>
          <form v-if="!admin" @submit.prevent="emit('login')" class="admin-login-form">
            <label class="field-label" for="admin-password">Web-Administrationspasswort</label>
            <input
              id="admin-password"
              class="settings-input"
              v-model="cloudAdminPassword"
              type="password"
              autocomplete="current-password"
              placeholder="Admin-Anmeldung"
              :disabled="!secure"
            />
            <button
              type="submit"
              class="outlined-action"
              :disabled="!secure || adminBusy || !cloudAdminPassword"
            >
              <ShieldCheck :size="17" />
              {{ adminBusy ? 'Anmeldung läuft …' : 'Als Administrator anmelden' }}
            </button>
            <p v-if="adminLoginError" role="alert" class="read-error">{{ adminLoginError }}</p>
          </form>
          <button v-else type="button" class="outlined-action" @click="emit('logout')">
            <ShieldCheck :size="17" /> Admin abmelden
          </button>
        </div>
        <form class="cloud-form" @submit.prevent="saveCloudSettings">
          <button
            type="button"
            class="outlined-action account-load"
            :disabled="accountLoading || !cloudStatus?.admin_enabled || !secure || !admin"
            @click="loadStoredAccount"
          >
            <ShieldCheck :size="17" />
            {{
              accountLoading ? 'Prüfe Adminzugang …' : 'Aktuelle E-Mail und Gerätekennung anzeigen'
            }}
          </button>
          <p v-if="accountLoaded" class="success-text">
            Gespeicherter Benutzer und deviceCode wurden in die beiden Felder unten übernommen. Das
            Cloud-Passwort bleibt verborgen.
          </p>
          <label class="field-label" for="cloud-username">WarmLink-Benutzername</label>
          <input
            id="cloud-username"
            class="settings-input"
            v-model="cloudUsername"
            autocomplete="off"
            placeholder="Leer = bisherigen Benutzer behalten"
            :disabled="!secure"
          />
          <label class="field-label" for="cloud-password">Cloud-Passwort</label>
          <input
            id="cloud-password"
            class="settings-input"
            v-model="cloudPassword"
            type="password"
            autocomplete="new-password"
            placeholder="Leer = bisheriges Passwort behalten"
            :disabled="!secure"
          />
          <label class="field-label" for="cloud-device">Gerätekennung (deviceCode)</label>
          <input
            id="cloud-device"
            class="settings-input"
            v-model="cloudDeviceCode"
            placeholder="Leer = bisherige Kennung behalten"
            :disabled="!secure"
          />
          <button
            class="main-action"
            type="submit"
            :disabled="cloudSaving || !cloudStatus?.admin_enabled || !secure || !admin"
          >
            {{ cloudSaving ? 'Speichert …' : 'Cloud-Einstellungen speichern' }}
          </button>
        </form>
        <div class="cloud-discovery">
          <button
            class="outlined-action"
            type="button"
            :disabled="cloudDiscovering || !cloudStatus?.admin_enabled || !secure || !admin"
            @click="discoverCloudDevices"
          >
            <Search :size="17" />
            {{ cloudDiscovering ? 'Suche läuft …' : 'Cloud-Geräte und Informationen abrufen' }}
          </button>
          <div v-if="cloudDevices.length" class="device-list">
            <button
              v-for="device in cloudDevices"
              :key="device.deviceCode"
              type="button"
              class="device-card"
              @click="cloudDeviceCode = device.deviceCode"
            >
              <strong>{{ device.deviceNickName || device.deviceName || 'PHNIX-Gerät' }}</strong>
              <span>Modell: {{ device.model || device.custModel || '—' }}</span>
              <span
                >Status: {{ device.deviceStatus ?? '—' }} · Fehler:
                {{ device.isFault === undefined ? '—' : device.isFault ? 'Ja' : 'Nein' }}</span
              >
              <span
                >DTU-Version: {{ device.dtuSoftwareVer || '—' }} · Signal:
                {{ device.dtuSignalIntensity ?? '—' }}</span
              >
              <span v-if="device.houseName">Haus: {{ device.houseName }}</span>
              <small>Auswählen</small>
            </button>
          </div>
        </div>
        <div class="cloud-discovery">
          <button
            type="button"
            class="outlined-action"
            :disabled="cloudStatusLoading || !cloudStatus?.admin_enabled || !secure || !admin"
            @click="queryCloudDeviceStatus"
          >
            <Activity :size="17" />
            {{
              cloudStatusLoading
                ? 'Frage Gerätestatus ab …'
                : 'Status des ausgewählten Cloud-Geräts abrufen'
            }}
          </button>
          <div v-if="Object.keys(selectedCloudStatus).length" class="device-status">
            <div v-for="(value, key) in selectedCloudStatus" :key="key">
              <span>{{ key }}</span><strong>{{ value ?? '—' }}</strong>
            </div>
          </div>
        </div>
        <p v-if="cloudMessage" role="status" class="success-text">{{ cloudMessage }}</p>
        <p v-if="cloudError" role="alert" class="read-error">{{ cloudError }}</p>
        <div class="cloud-discovery">
          <button
            type="button"
            class="outlined-action"
            :disabled="cloudScanLoading || !cloudStatus?.admin_enabled || !secure || !admin"
            @click="rescanCloud"
          >
            <RefreshCw :size="17" :class="{ spinning: cloudScanLoading }" /> Vollständigen
            Cloud-Katalog erneut abfragen
          </button>
          <p class="section-hint">
            {{ cloudOverview?.supported ?? 0 }} / {{ cloudOverview?.total ?? 0 }} Cloud-Codes mit
            Wert · Scanstatus: {{ cloudOverview?.status || 'unbekannt' }}
          </p>
        </div>
        <p class="section-hint">
          Geräteinformationen stammen aus Geräteliste und Hauszuordnungen. Cloud-Passwort und Token
          werden nicht aus dem Server ausgelesen.
        </p>
      </section>
      <section class="connection-section">
        <h2>Weitere lokale Busse</h2>
        <p class="section-hint">
          Standard-Modbus wird derzeit serverseitig eingerichtet. Display-Modbus ist noch nicht
          implementiert.
        </p>
      </section>
    </div>
  </dialog>
</template>
