<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  api,
  type Register,
  type RegisterValue,
  type SpecialDialog,
  type TransportId,
} from '../api'
import ParameterEditor from './ParameterEditor.vue'
import HeatingCurve from './HeatingCurve.vue'

const props = defineProps<{
  dialog: SpecialDialog
  transport: TransportId
  admin: boolean
  valueFor: (register: number) => RegisterValue | null
}>()
const emit = defineEmits<{ updated: [] }>()
const definitions = ref<Register[]>([])
const error = ref('')
let generation = 0
watch(
  () => props.dialog.id,
  async () => {
    const request = ++generation
    definitions.value = []
    try {
      const ids =
        (props.transport === 'cloud'
          ? props.dialog.registers
          : (props.dialog.local_registers ?? props.dialog.registers)) || []
      if (!ids.length) return
      const result = await api.registers('', '', ids)
      if (request !== generation) return
      definitions.value = ids.flatMap((id) => result.items.filter((row) => row.register === id))
    } catch (failure) {
      if (request === generation)
        error.value = failure instanceof Error ? failure.message : 'Parameter nicht verfügbar'
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => generation++)

const atMode = computed(() => {
  const row = props.valueFor(1236)
  const value = row?.raw ?? row?.value
  return value == null || value === '' ? null : Number(value)
})
const visibleDefinitions = computed(() => {
  if (props.dialog.id !== 'at') return definitions.value
  const visible = [1236]
  if (atMode.value === 1) visible.push(1234, 1235, 1164, 1165)
  if (atMode.value === 2)
    visible.push(1164, 1165, ...(props.dialog.curve_points ?? []).map((point) => point.register))
  return definitions.value.filter((entry) => visible.includes(entry.register))
})
function faults(entry: Register) {
  const raw = props.valueFor(entry.register)?.raw
  if (raw == null) return []
  return Array.from({ length: 16 }, (_, bit) => bit)
    .filter((bit) => (raw & (1 << bit)) !== 0)
    .map((bit) => entry.bit_map?.[String(bit)] || 'Unbekannte Meldung (Bit ' + bit + ')')
}
const sourceLabels: Record<string, string> = {
  cloud: 'Cloud',
  warmlink_raw: 'LTE-Modbus',
  standard_modbus: 'Standard-Modbus',
  display_modbus: 'Display-Modbus',
}
function settingAge(register: number) {
  const row = props.valueFor(register)
  if (!row) return null
  return Date.now() - Date.parse(row.timestamp)
}
function isStale(register: number) {
  if (register >= 2000) return props.valueFor(register)?.quality === 'stale'
  return (settingAge(register) ?? 0) > 12 * 60 * 60 * 1000
}
function display(register: number) {
  const row = props.valueFor(register)
  return row?.display_value ?? row?.value ?? '—'
}
</script>

<template>
  <div class="special-control-scroll">
    <p v-if="error" class="read-error">{{ error }}</p>
    <HeatingCurve
      v-if="dialog.id === 'at' && (atMode === 1 || atMode === 2)"
      :mode="atMode"
      :points="dialog.curve_points ?? []"
      :registers="definitions"
      :transport="transport"
      :admin="admin"
      :value-for="valueFor"
      @updated="emit('updated')"
    />
    <div class="special-card-grid">
      <article
        v-for="entry in visibleDefinitions"
        :key="entry.register"
        class="special-control-card"
      >
        <span class="register-code">{{ entry.code || 'Register ' + entry.register }}</span>
        <h3>{{ entry.name }}</h3>
        <p class="special-current" :class="{ 'is-stale': isStale(entry.register) }">
          {{ display(entry.register) }} <small>{{ valueFor(entry.register)?.unit || '' }}</small>
        </p>
        <small v-if="valueFor(entry.register)" class="section-hint">
          {{
            sourceLabels[valueFor(entry.register)!.transport] || valueFor(entry.register)!.transport
          }}
          · {{ new Date(valueFor(entry.register)!.timestamp).toLocaleString('de-DE') }}
          <template v-if="isStale(entry.register)"> · veraltet</template>
        </small>
        <template v-if="dialog.id === 'fault' && valueFor(entry.register)?.raw != null">
          <ul v-if="faults(entry).length">
            <li v-for="(text, index) in faults(entry)" :key="index">{{ text }}</li>
          </ul>
          <small v-else-if="valueFor(entry.register)?.quality !== 'stale'"
            >Keine aktiven Bits in diesem Register</small
          >
        </template>
        <details v-if="entry.description">
          <summary>Beschreibung & Hinweise</summary>
          <p class="parameter-description">{{ entry.description }}</p>
        </details>
        <ParameterEditor
          v-if="entry.write_available && !dialog.read_only && transport !== 'display_modbus'"
          :register="entry"
          :transport="transport"
          :admin="admin"
          :value="valueFor(entry.register)"
          @updated="emit('updated')"
          @read="emit('updated')"
        />
        <small v-else>Lesender Statuswert</small>
      </article>
    </div>
    <p v-if="!definitions.length && !error" class="section-hint">Parameter werden geladen …</p>
  </div>
</template>
