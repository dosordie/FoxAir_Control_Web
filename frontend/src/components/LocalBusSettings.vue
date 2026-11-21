<script setup lang="ts">
import BusLinkFields from './BusLinkFields.vue'
import { ref, watch, onBeforeUnmount } from 'vue'
import type { TransportId } from '../api'
type Bus = 'display_modbus' | 'standard_modbus'
const props = defineProps<{ bus: Bus; admin: boolean; secure: boolean; open: boolean }>()
const emit = defineEmits<{ changed: [transport: TransportId] }>()
type Config = {
  medium: 'tcp' | 'serial'
  serial_device: string
  baudrate: number
  host: string
  port: number
  slave: number
  timeout: number
  enabled: boolean
  connection_mode: 'browser' | 'permanent'
  browser_timeout_seconds: number
}
const defaults = (bus: Bus): Config => ({
  medium: 'tcp',
  serial_device: '',
  baudrate: bus === 'display_modbus' ? 4800 : 9600,
  host: '',
  port: 2001,
  slave: bus === 'display_modbus' ? 3 : 99,
  timeout: 2,
  enabled: false,
  connection_mode: 'browser',
  browser_timeout_seconds: 90,
})
const bus = props.bus
const config = ref(defaults(bus))
const busy = ref(false),
  message = ref('')
async function call(save = false) {
  const r = await fetch('/api/local/' + bus + '/config' + (save ? '/save' : ''), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-FoxAir-Admin': '1' },
    body: JSON.stringify(save ? config.value : {}),
  })
  const data = await r.json()
  if (!r.ok)
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Konfiguration nicht verfügbar')
  return { ...defaults(bus), ...data } as Config
}
let epoch = 0
onBeforeUnmount(() => {
  epoch++
})
watch(
  () => [props.open, props.admin, props.secure],
  async () => {
    const request = ++epoch
    message.value = ''
    if (!props.open || !props.admin || !props.secure) {
      busy.value = false
      config.value = defaults(bus)
      return
    }
    busy.value = true
    try {
      const value = await call()
      if (request === epoch) config.value = value
    } catch (e) {
      if (request === epoch) message.value = String(e)
    } finally {
      if (request === epoch) busy.value = false
    }
  },
  { immediate: true },
)
async function save() {
  if (!props.admin || !props.secure || !props.open || busy.value) return
  const request = epoch
  busy.value = true
  message.value = ''
  try {
    const value = await call(true)
    if (request !== epoch) return
    config.value = value
    emit('changed', bus)
    message.value = 'Anschluss gespeichert'
  } catch (e) {
    if (request === epoch) message.value = String(e)
  } finally {
    if (request === epoch) busy.value = false
  }
}
</script>
<template>
  <section class="connection-section">
    <h2>{{ bus === 'display_modbus' ? 'Modbus-Display' : 'Modbus-Standard' }}</h2>
    <p v-if="bus === 'display_modbus'" class="section-hint">
      Passiver Empfang am Displaybus über USB-RS485 oder einen transparenten TCP-Adapter. Keine
      Parameterwrites. Nur „Alle Werte vom Bus lesen“ darf die feste Display-Spezialabfrage senden.
    </p>
    <p v-else class="section-hint">
      Eigener Modbus-RTU-Anschluss über USB-RS485 oder transparentes TCP, etwa ser2net. Die Web-App
      ist hier der aktive Master.
    </p>
    <form @submit.prevent="save()">
      <fieldset
        :disabled="!admin || !secure || busy"
        style="border: 0; padding: 0; display: grid; gap: 12px; min-width: 0"
      >
        <BusLinkFields
          v-model:medium="config.medium"
          v-model:host="config.host"
          v-model:port="config.port"
          v-model:serial-device="config.serial_device"
          v-model:baudrate="config.baudrate"
        />
        <label
          >Modbus-Teilnehmer<input
            class="settings-input"
            type="number"
            min="1"
            max="247"
            v-model.number="config.slave"
            :disabled="bus === 'display_modbus'" /></label
        ><label
          >Antwort-Timeout (Sekunden)<input
            class="settings-input"
            type="number"
            min="0.25"
            max="10"
            step="0.25"
            v-model.number="config.timeout"
        /></label>
        <template v-if="bus === 'display_modbus'"
          ><label
            >Empfang offen halten<select class="settings-input" v-model="config.connection_mode">
              <option value="browser">Solange ein Browser verbunden ist</option>
              <option value="permanent">Dauerhaft auf dem Server</option>
            </select></label
          ></template
        >
        <p v-else class="section-hint">
          Verbindung bleibt offen, solange ein Browser verbunden ist.
        </p>
        <label v-if="bus === 'standard_modbus' || config.connection_mode === 'browser'"
          >Nach letztem Browser-Lebenszeichen schließen (Sekunden)<input
            class="settings-input"
            type="number"
            min="30"
            max="3600"
            v-model.number="config.browser_timeout_seconds"
        /></label>
        <label><input type="checkbox" v-model="config.enabled" /> Anschluss aktivieren</label
        ><button class="outlined-action" type="submit">
          {{ busy ? 'Speichert …' : 'Anschluss speichern' }}
        </button>
      </fieldset>
    </form>
  </section>
  <p v-if="message" role="status" class="section-hint">{{ message }}</p>
</template>
