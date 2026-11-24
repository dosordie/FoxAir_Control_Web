<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { giraIcon, giraIcons } from '../giraIcons'
import type { GiraItem } from '../api'
const emit = defineEmits<{ values: [GiraItem[]]; saved: [] }>()
const props = defineProps<{ settings?: boolean; admin?: boolean; secure?: boolean }>()
type Config = {
  enabled: boolean
  host: string
  port: number
  tls: boolean
  path: string
  username: string
  password: string
  password_configured?: boolean
  clear_password: boolean
  auth_header: boolean
  objects: { key: string; name: string; unit: string; text_encoding?: string; icon?: string }[]
}
type State = {
  enabled: boolean
  connected: boolean
  error: string | null
  items: {
    layout_key: string
    id: number
    name: string
    icon?: string
    unit: string
    value: number | string | null
    timestamp: string | null
    quality: string
  }[]
}
const empty = (): Config => ({
  enabled: false,
  host: '',
  port: 80,
  tls: false,
  path: '/',
  username: '',
  password: '',
  clear_password: false,
  auth_header: false,
  objects: [],
})
const cfg = ref(empty()),
  state = ref<State>({ enabled: false, connected: false, error: null, items: [] })
watch(
  () => state.value.items,
  (items) => emit('values', items),
)
const open = ref(false),
  busy = ref(false),
  message = ref('')
let epoch = 0,
  disposed = false,
  timer: ReturnType<typeof setTimeout> | undefined
async function request(path: string, body?: unknown) {
  const response = await fetch(
    '/api/expert/gira/' + path,
    body === undefined
      ? {}
      : {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-FoxAir-Admin': '1' },
          body: JSON.stringify(body),
        },
  )
  const data = await response.json()
  if (!response.ok)
    throw Object.assign(
      new Error(typeof data.detail === 'string' ? data.detail : 'Gira-Anfrage fehlgeschlagen'),
      { status: response.status },
    )
  return data
}
async function load() {
  if (!props.admin || !props.secure || !open.value) return
  const version = ++epoch
  busy.value = true
  try {
    const data = await request('config', {})
    if (!disposed && version === epoch)
      cfg.value = {
        ...data,
        objects: data.objects.map((item: Config['objects'][number]) => ({
          ...item,
          text_encoding: item.text_encoding || 'auto',
          icon: item.icon || 'knx',
        })),
      }
  } catch (error) {
    if (!disposed && version === epoch) message.value = String(error)
  } finally {
    if (!disposed && version === epoch) busy.value = false
  }
}
async function save() {
  if (!props.admin || !props.secure || busy.value) return
  const version = epoch
  busy.value = true
  message.value = ''
  try {
    await request('save', cfg.value)
    if (!disposed && version === epoch) {
      cfg.value.password = ''
      cfg.value.clear_password = false
      message.value = 'Experteneinstellungen gespeichert'
      emit('saved')
      await load()
    }
  } catch (error) {
    if (!disposed && version === epoch) message.value = String(error)
  } finally {
    if (!disposed && version === epoch) busy.value = false
  }
}
watch(
  () => [props.admin, props.secure, open.value],
  () => {
    epoch++
    cfg.value = empty()
    message.value = ''
    busy.value = false
    void load()
    clearTimeout(timer)
    if (open.value) {
      void refresh()
    }
  },
)
async function refresh() {
  try {
    const data = await request('state')
    if (!disposed) state.value = data
  } catch (error) {
    if (!disposed) {
      const denied = [401, 403].includes(Number((error as { status?: number }).status))
      state.value = denied
        ? { enabled: false, connected: false, error: null, items: [] }
        : {
            ...state.value,
            connected: false,
            error: 'Keine Verbindung zum Webserver',
            items: state.value.items.map((item) => ({ ...item, quality: 'stale' })),
          }
    }
  }
  if (!disposed && (!props.settings || open.value))
    timer = setTimeout(refresh, state.value.enabled ? 2000 : 30000)
}
const display = (value: number | string | null) =>
  value === null
    ? '—'
    : typeof value === 'number'
      ? value.toLocaleString('de-DE', { maximumFractionDigits: 3 })
      : value
onMounted(() => {
  if (!props.settings) void refresh()
})
onBeforeUnmount(() => {
  disposed = true
  epoch++
  cfg.value.password = ''
  clearTimeout(timer)
})
</script>
<template>
  <details
    v-if="settings"
    class="panel expert-settings"
    @toggle="open = ($event.target as HTMLDetailsElement).open"
  >
    <summary>Experteneinstellungen</summary>
    <div v-if="open">
      <p class="section-hint" role="status">
        {{
          state.error ||
          (state.connected
            ? 'Gira verbunden'
            : state.enabled
              ? 'Gira verbindet …'
              : 'Gira deaktiviert')
        }}
      </p>
      <h2>Gira HomeServer · zusätzliche Anzeigen</h2>
      <p class="section-hint">
        Rein lesende WebSocket-Abonnements. Diese Werte sind für dieselben Benutzer sichtbar wie die
        Wärmepumpenwerte.
      </p>
      <form @submit.prevent="save">
        <fieldset :disabled="!admin || !secure || busy">
          <label><input type="checkbox" v-model="cfg.enabled" /> Gira-Anzeigen aktivieren</label>
          <template v-if="cfg.enabled">
            <label
              >HomeServer-IP<input
                class="settings-input"
                v-model="cfg.host"
                placeholder="Private IP-Adresse"
            /></label>
            <label
              >Port<input
                class="settings-input"
                type="number"
                min="1"
                max="65535"
                v-model.number="cfg.port"
            /></label>
            <label
              >WebSocket-Pfad<input class="settings-input" v-model="cfg.path" placeholder="/"
            /></label>
            <label
              ><input type="checkbox" v-model="cfg.tls" /> TLS (wss; vertrauenswürdiges Zertifikat
              erforderlich)</label
            >
            <label
              >Benutzername<input class="settings-input" v-model="cfg.username" autocomplete="off"
            /></label>
            <label
              >Passwort<input
                class="settings-input"
                type="password"
                v-model="cfg.password"
                autocomplete="new-password"
                :placeholder="
                  cfg.password_configured ? 'Leer = gespeichertes Passwort behalten' : ''
                "
            /></label>
            <label
              ><input type="checkbox" v-model="cfg.clear_password" /> Gespeichertes Passwort
              entfernen</label
            >
            <label
              ><input type="checkbox" v-model="cfg.auth_header" /> Anmeldung als HTTP-Header senden
              (sonst Gira-URL-Verfahren)</label
            >
            <div v-for="(object, index) in cfg.objects" :key="index" class="expert-object">
              <label
                >Objektschlüssel<input
                  class="settings-input"
                  v-model="object.key"
                  placeholder="CO@123"
                  required
              /></label>
              <label
                >Bezeichnung (optional)<input
                  class="settings-input"
                  v-model="object.name"
                  maxlength="60"
              /></label>
              <label
                >Einheit (optional)<input
                  class="settings-input"
                  v-model="object.unit"
                  maxlength="16"
              /></label>
              <label
                >Symbol <component :is="giraIcon(object.icon)" :size="20" aria-hidden="true" />
                <select v-model="object.icon" class="settings-input">
                  <option v-for="(entry, key) in giraIcons" :key="key" :value="key">
                    {{ entry[1] }}
                  </option>
                </select>
              </label>
              <label
                >Textdarstellung<select class="settings-input" v-model="object.text_encoding">
                  <option value="auto">Automatisch (UTF-8/Base64)</option>
                  <option value="plain">Klartext unverändert</option>
                  <option value="utf8">Base64 / UTF-8</option>
                  <option value="latin1">Base64 / Latin-1 (ältere Geräte)</option>
                </select></label
              >
              <button type="button" class="outlined-action" @click="cfg.objects.splice(index, 1)">
                Objekt entfernen
              </button>
            </div>
            <button
              type="button"
              class="outlined-action"
              :disabled="cfg.objects.length >= 24"
              @click="
                cfg.objects.push({
                  key: '',
                  name: '',
                  unit: '',
                  text_encoding: 'auto',
                  icon: 'knx',
                })
              "
            >
              Objekt hinzufügen
            </button>
          </template>
          <button class="main-action" type="submit">
            {{ busy ? 'Speichert …' : 'Experteneinstellungen speichern' }}
          </button>
        </fieldset>
      </form>
      <p role="status" class="section-hint">{{ message }}</p>
    </div>
  </details>
  <div v-else-if="state.enabled" class="expert-metrics">
    <div class="power-summary">
      <div
        v-for="item in state.items"
        :key="item.id"
        :class="{ 'is-stale': item.quality === 'stale' }"
        :title="
          item.timestamp
            ? new Date(item.timestamp).toLocaleString('de-DE')
            : 'Noch kein Wert empfangen'
        "
      >
        <component :is="giraIcon(item.icon)" :size="17" aria-hidden="true" />
        <strong
          >{{ display(item.value) }} <small v-if="item.unit">{{ item.unit }}</small></strong
        ><small v-if="item.name">{{ item.name }}</small>
      </div>
    </div>
  </div>
</template>
