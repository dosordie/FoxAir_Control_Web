<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import type { TransportId } from '../api'
const props = defineProps<{ admin: boolean; secure: boolean; open: boolean }>()
const emit = defineEmits<{ changed: [transport: TransportId] }>()
type Bus = 'display_modbus' | 'standard_modbus'
type Config = {
  host: string
  port: number
  slave: number
  timeout: number
  enabled: boolean
  connection_mode: 'browser' | 'permanent'
  browser_timeout_seconds: number
}
const defaults = (bus: Bus): Config => ({
  host: '',
  port: 2001,
  slave: bus === 'display_modbus' ? 3 : 99,
  timeout: 2,
  enabled: false,
  connection_mode: 'browser',
  browser_timeout_seconds: 90,
})
const configs = ref<Record<Bus, Config>>({
  display_modbus: defaults('display_modbus'),
  standard_modbus: defaults('standard_modbus'),
})
const kinds: Bus[] = ['display_modbus', 'standard_modbus']
const busy = ref(false),
  message = ref('')
async function call(bus: Bus, save = false) {
  const r = await fetch('/api/local/' + bus + '/config' + (save ? '/save' : ''), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-FoxAir-Admin': '1' },
    body: JSON.stringify(save ? configs.value[bus] : {}),
  })
  const data = await r.json()
  if (!r.ok)
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Konfiguration nicht verfügbar')
  return data as Config
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
      configs.value = {
        display_modbus: defaults('display_modbus'),
        standard_modbus: defaults('standard_modbus'),
      }
      return
    }
    busy.value = true
    try {
      const next = {
        display_modbus: defaults('display_modbus'),
        standard_modbus: defaults('standard_modbus'),
      }
      for (const bus of kinds) {
        const value = await call(bus)
        if (request !== epoch) return
        next[bus] = value
      }
      configs.value = next
    } catch (e) {
      if (request === epoch) message.value = String(e)
    } finally {
      if (request === epoch) busy.value = false
    }
  },
  { immediate: true },
)
async function save(bus: Bus) {
  if (!props.admin || !props.secure || !props.open || busy.value) return
  const request = epoch
  busy.value = true
  message.value = ''
  try {
    const value = await call(bus, true)
    if (request !== epoch) return
    configs.value[bus] = value
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
  <section v-for="bus in kinds" :key="bus" class="connection-section">
    <h2>{{ bus === 'display_modbus' ? 'Display-Modbus' : 'Standard-Modbus' }}</h2>
    <p v-if="bus === 'display_modbus'" class="section-hint">
      Passiver Empfang über einen transparenten RTU/TCP-Adapter am Displaybus. Keine
      Parameterwrites. Nur „Alle Werte vom Bus lesen“ darf die feste Display-Spezialabfrage senden.
    </p>
    <p v-else class="section-hint">
      Eigener Standard-Modbus-Anschluss über transparentes RTU-over-TCP, etwa ser2net. Kein Modbus
      TCP mit MBAP-Header. Die Web-App ist hier der aktive Master.
    </p>
    <form @submit.prevent="save(bus)">
      <fieldset
        :disabled="!admin || !secure || busy"
        style="border: 0; padding: 0; display: grid; gap: 12px; min-width: 0"
      >
        <label
          >IP-Adresse<input
            class="settings-input"
            v-model="configs[bus].host"
            placeholder="IP des TCP-/RS485-Adapters"
            autocomplete="off" /></label
        ><label
          >TCP-Port<input
            class="settings-input"
            type="number"
            min="1"
            max="65535"
            v-model.number="configs[bus].port" /></label
        ><label
          >Modbus-Teilnehmer<input
            class="settings-input"
            type="number"
            min="1"
            max="247"
            v-model.number="configs[bus].slave"
            :disabled="bus === 'display_modbus'" /></label
        ><label
          >Antwort-Timeout (Sekunden)<input
            class="settings-input"
            type="number"
            min="0.25"
            max="10"
            step="0.25"
            v-model.number="configs[bus].timeout"
        /></label>
        <template v-if="bus === 'display_modbus'"
          ><label
            >Empfang offen halten<select
              class="settings-input"
              v-model="configs[bus].connection_mode"
            >
              <option value="browser">Solange ein Browser verbunden ist</option>
              <option value="permanent">Dauerhaft auf dem Server</option>
            </select></label
          ><label
            >Browser-Sitzung nach letzter Verbindung (Sekunden)<input
              class="settings-input"
              type="number"
              min="30"
              max="3600"
              v-model.number="configs[bus].browser_timeout_seconds" /></label
        ></template>
        <label><input type="checkbox" v-model="configs[bus].enabled" /> Anschluss aktivieren</label
        ><button class="outlined-action" type="submit">
          {{ busy ? 'Speichert …' : 'Anschluss speichern' }}
        </button>
      </fieldset>
    </form>
  </section>
  <p v-if="message" role="status" class="section-hint">{{ message }}</p>
</template>
