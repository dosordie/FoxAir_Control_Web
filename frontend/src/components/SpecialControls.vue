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
      const ids = props.dialog.registers || []
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

function number(register: number) {
  const row = props.valueFor(register)
  if (!row || row.value == null) return null
  const value =
    register === 1236 && row.raw != null ? row.raw : Number(String(row.value).replace(',', '.'))
  return Number.isFinite(value) ? value : null
}
const curve = computed(() => {
  const mode = number(1236),
    minimum = number(1164),
    maximum = number(1165)
  if (!mode || minimum == null || maximum == null || minimum > maximum) return []
  const slope = number(1234),
    offset = number(1235)
  const points = props.dialog.curve_points || []
  const targets = points.map((point) =>
    mode === 2
      ? number(point.register)
      : mode === 1 && slope != null && offset != null
        ? offset - slope * point.outdoor
        : null,
  )
  if (targets.some((value) => value == null)) return []
  return points.map((point, index) => {
    const value = Math.max(minimum, Math.min(maximum, targets[index]!))
    return {
      ...point,
      value,
      x: 50 + ((point.outdoor + 20) / 40) * 420,
      y: 200 - ((value - minimum) / Math.max(1, maximum - minimum)) * 170,
    }
  })
})
const path = computed(() =>
  curve.value.map((point, index) => (index ? 'L' : 'M') + point.x + ',' + point.y).join(' '),
)
function display(register: number) {
  const row = props.valueFor(register)
  return row?.display_value ?? row?.value ?? '—'
}
</script>

<template>
  <div class="special-control-scroll">
    <p v-if="error" class="read-error">{{ error }}</p>
    <section v-if="dialog.id === 'at'" class="curve-panel" aria-label="Heizkennlinie">
      <h3>Heizkennlinie</h3>
      <p>Außen: {{ display(2048) }} °C · Aktueller Sollwert: {{ display(2014) }} °C</p>
      <svg
        v-if="curve.length"
        viewBox="0 0 520 250"
        role="img"
        aria-label="Heizsollwert über Außentemperatur, begrenzt durch R10 und R11"
      >
        <path d="M50 20 V200 H490" fill="none" stroke="#a8b0b9" />
        <path :d="path" fill="none" stroke="#ec8735" stroke-width="4" />
        <g v-for="point in curve" :key="point.register">
          <circle :cx="point.x" :cy="point.y" r="5" fill="#ec8735">
            <title>{{ point.outdoor }} °C außen: {{ point.value }} °C Sollwert</title>
          </circle>
          <text :x="point.x" y="225" text-anchor="middle">{{ point.outdoor }}°</text>
          <text :x="point.x" :y="point.y - 12" text-anchor="middle">
            {{ point.value.toLocaleString('de-DE', { maximumFractionDigits: 1 }) }}°
          </text>
        </g>
      </svg>
      <p v-else class="section-hint">
        Kennlinie ausgeschaltet oder Kurvenwerte / R10–R11 noch nicht vollständig verfügbar.
      </p>
    </section>
    <div class="special-card-grid">
      <article v-for="entry in definitions" :key="entry.register" class="special-control-card">
        <span class="register-code">{{ entry.code || 'Register ' + entry.register }}</span>
        <h3>{{ entry.name }}</h3>
        <p
          class="special-current"
          :class="{ 'is-stale': valueFor(entry.register)?.quality === 'stale' }"
        >
          {{ display(entry.register) }} <small>{{ valueFor(entry.register)?.unit || '' }}</small>
        </p>
        <details v-if="entry.description">
          <summary>Beschreibung & Hinweise</summary>
          <p class="parameter-description">{{ entry.description }}</p>
        </details>
        <ParameterEditor
          v-if="entry.write_available"
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
