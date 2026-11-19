<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronRight, Search, ArrowRight } from 'lucide-vue-next'
import type { RegisterValue, TransportId } from '../api'
const props = defineProps<{ rows: RegisterValue[]; transport: TransportId }>()
const emit = defineEmits<{ parameters: [] }>()
const open = ref(false)
const query = ref('')
type History = {
  current: string
  previous: string
  stamp: string
  version: number
  changedAt: number
}
const history = ref<Record<number, History>>({})
let source: TransportId | undefined
const text = (row: RegisterValue) => `${row.display_value ?? row.value} ${row.unit || ''}`.trim()
// Track only this browser's received values. Timestamp-only updates do not flash.
watch(
  () => [props.transport, props.rows] as const,
  () => {
    if (source !== props.transport) {
      history.value = {}
      source = props.transport
    }
    for (const row of props.rows) {
      const prior = history.value[row.register]
      if (prior && Date.parse(row.timestamp) < Date.parse(prior.stamp)) continue
      const current = text(row)
      history.value[row.register] = {
        current,
        previous: prior && prior.current !== current ? prior.current : prior?.previous || '—',
        stamp: row.timestamp,
        changedAt: prior && prior.current !== current ? Date.now() : prior?.changedAt || 0,
        version: (prior?.version || 0) + (prior && prior.current !== current ? 1 : 0),
      }
    }
  },
  { deep: true, immediate: true },
)
const rows = computed(() => {
  const term = query.value.trim().toLocaleLowerCase('de')
  const unique = new Map<number, RegisterValue>()
  for (const row of props.rows) {
    if (!Number.isInteger(row.register) || row.value == null) continue
    const previous = unique.get(row.register)
    if (!previous || Date.parse(row.timestamp) >= Date.parse(previous.timestamp))
      unique.set(row.register, row)
  }
  return [...unique.values()]
    .filter(
      (row) =>
        !term ||
        [row.register, row.code, row.name].some((value) =>
          String(value || '')
            .toLocaleLowerCase('de')
            .includes(term),
        ),
    )
    .sort((a, b) => a.register - b.register)
})
function area(register: number) {
  if (register >= 91000 && register < 91200) return 'inverter'
  if (register >= 1000 && register < 1600) return 'settings'
  if (register >= 2000 && register < 3000) return 'status'
  if (register >= 3000) return 'display'
  return 'other'
}
</script>
<template>
  <section class="panel main-register-preview">
    <button
      class="register-preview-toggle"
      type="button"
      @click="open = !open"
      :aria-expanded="open"
    >
      <span
        ><span class="section-caption">REGISTER / FOXAIR_CONTROL</span
        ><strong>Registerübersicht im Hauptfenster</strong></span
      >
      <span
        >{{ open ? 'Schließen' : 'Anzeigen' }}
        <ChevronRight :size="17" :class="{ 'is-open': open }"
      /></span>
    </button>
    <template v-if="open">
      <label class="search-box"
        ><Search :size="17" /><input
          v-model="query"
          placeholder="Register oder Code suchen"
          aria-label="Hauptfenster Register filtern"
      /></label>
      <p class="browser-legend">
        <span>Einstellungen</span><span>Status</span> · {{ rows.length }} empfangene Register
      </p>
      <div
        class="register-browser-scroll"
        role="region"
        aria-label="Empfangene Modbus-Register"
        tabindex="0"
      >
        <table class="register-browser-table">
          <thead>
            <tr>
              <th>Register</th>
              <th>Bezeichnung</th>
              <th>Aktuell</th>
              <th title="Vorheriger abweichender Wert seit Öffnen dieser Übersicht">
                Letzter Wert
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.register + '-' + (history[row.register]?.version || 0)"
              :class="[
                'area-' + area(row.register),
                {
                  'register-changed': Date.now() - (history[row.register]?.changedAt || 0) < 1000,
                  'is-stale': row.quality === 'stale',
                },
              ]"
            >
              <td>{{ row.register }}</td>
              <td>
                {{ row.name || 'Register ' + row.register
                }}<small v-if="row.code">{{ row.code }}</small>
              </td>
              <td :title="new Date(row.timestamp).toLocaleString('de-DE')">{{ text(row) }}</td>
              <td class="previous-register-value">{{ history[row.register]?.previous || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!rows.length" class="empty-state">Noch keine Registerwerte vorhanden.</p>
      </div>
      <button class="outlined-action" type="button" @click="emit('parameters')">
        Alle Parameter öffnen <ArrowRight :size="16" />
      </button>
    </template>
  </section>
</template>
