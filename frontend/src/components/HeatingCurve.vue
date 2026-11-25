<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Register, RegisterValue, TransportId } from '../api'
import ParameterEditor from './ParameterEditor.vue'

type CurvePoint = { outdoor: number; register: number }
type Sample = { outdoor: number; target: number }
const props = defineProps<{
  points: CurvePoint[]
  registers: Register[]
  transport: TransportId
  admin: boolean
  valueFor: (register: number) => RegisterValue | null
}>()
const emit = defineEmits<{ updated: [] }>()
const plot = { left: 62, right: 492, top: 24, bottom: 198 }
const graphic = ref<SVGSVGElement>()
const drafts = ref<Record<number, number>>({})
const selectedRegister = ref<number | null>(null)
const drag = ref<{ pointer: number; register: number; previous?: number; startY: number }>()
const format = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 })

function readNumber(register: number) {
  const row = props.valueFor(register)
  const value = register === 1236 ? (row?.raw ?? row?.value) : row?.value
  if (value == null || String(value).trim() === '') return null
  const result = Number(String(value).replace(',', '.'))
  return Number.isFinite(result) ? result : null
}
const mode = computed(() => readNumber(1236))
const limits = computed(() => {
  const min = readNumber(1164)
  const max = readNumber(1165)
  return min != null && max != null && min <= max ? { min, max } : null
})
const samples = computed(() => {
  if (mode.value === 1) {
    const slope = readNumber(1234)
    const offset = readNumber(1235)
    return slope == null || offset == null
      ? []
      : [-20, 20].map((outdoor) => ({ outdoor, target: offset - slope * outdoor }))
  }
  if (mode.value !== 2 || props.points.length !== 7) return []
  const rows = props.points.map((point) => ({
    ...point,
    target: drafts.value[point.register] ?? readNumber(point.register),
  }))
  return rows.every((point) => point.target != null) ? (rows as (CurvePoint & Sample)[]) : []
})
const line = computed(() => {
  const bounds = limits.value
  const points = samples.value
  if (!bounds || !points.length) return ''
  const clipped = (target: number) => Math.min(bounds.max, Math.max(bounds.min, target))
  const coordinates: Sample[] = []
  for (const [index, point] of points.entries()) {
    const previous = points[index - 1]
    if (previous && previous.target !== point.target) {
      const crossings = [bounds.min, bounds.max]
        .map((target) => ({
          target,
          portion: (target - previous.target) / (point.target - previous.target),
        }))
        .filter(({ portion }) => portion > 0 && portion < 1)
        .sort((left, right) => left.portion - right.portion)
      for (const { target, portion } of crossings) {
        coordinates.push({
          target,
          outdoor: previous.outdoor + portion * (point.outdoor - previous.outdoor),
        })
      }
    }
    coordinates.push({ ...point, target: clipped(point.target) })
  }
  return coordinates.map((point) => x(point.outdoor) + ',' + y(point.target)).join(' ')
})
const markers = computed(() => (mode.value === 2 ? samples.value.filter(hasRegister) : []))
function hasRegister(point: Sample): point is CurvePoint & Sample {
  return 'register' in point
}
const writableRegisters = computed(
  () =>
    new Set(
      props.registers.filter((entry) => entry.write_available).map((entry) => entry.register),
    ),
)
const canDrag = computed(
  () =>
    props.admin &&
    ['cloud', 'warmlink_raw', 'standard_modbus'].includes(props.transport) &&
    mode.value === 2 &&
    !!limits.value &&
    limits.value.min < limits.value.max,
)
function editable(register: number) {
  return canDrag.value && writableRegisters.value.has(register)
}
const activeRegister = computed(() =>
  props.registers.find((entry) => entry.register === selectedRegister.value),
)
const activePoint = computed(() =>
  props.points.find((point) => point.register === selectedRegister.value),
)
const yTicks = computed(() => {
  if (!limits.value) return []
  const { min, max } = limits.value
  return min === max ? [min] : [min, (min + max) / 2, max]
})
function x(outdoor: number) {
  return plot.left + ((outdoor + 20) / 40) * (plot.right - plot.left)
}
function y(target: number) {
  const bounds = limits.value
  if (!bounds) return plot.bottom
  if (bounds.min === bounds.max) return (plot.top + plot.bottom) / 2
  const clipped = Math.min(bounds.max, Math.max(bounds.min, target))
  return (
    plot.bottom - ((clipped - bounds.min) / (bounds.max - bounds.min)) * (plot.bottom - plot.top)
  )
}

function select(register: number) {
  if (editable(register)) selectedRegister.value = register
}
function startDrag(register: number, event: PointerEvent) {
  if (!editable(register) || event.button !== 0 || !event.isPrimary) return
  select(register)
  drag.value = {
    pointer: event.pointerId,
    register,
    previous: drafts.value[register],
    startY: event.clientY,
  }
  const handle = event.currentTarget as SVGElement
  handle.setPointerCapture(event.pointerId)
}
function trackDrag(event: PointerEvent) {
  const state = drag.value
  const bounds = limits.value
  const matrix = graphic.value?.getScreenCTM()
  if (
    !state ||
    event.pointerId !== state.pointer ||
    !bounds ||
    !matrix ||
    !editable(state.register)
  )
    return
  if (Math.abs(event.clientY - state.startY) < 2 && drafts.value[state.register] === state.previous)
    return
  const localY = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse()).y
  const target =
    bounds.min + ((plot.bottom - localY) / (plot.bottom - plot.top)) * (bounds.max - bounds.min)
  drafts.value[state.register] = Math.min(
    bounds.max,
    Math.max(bounds.min, Math.round(target * 10) / 10),
  )
}
function stopDrag(event: PointerEvent, canceled = false) {
  const state = drag.value
  if (!state || event.pointerId !== state.pointer) return
  if (canceled) {
    if (state.previous == null) delete drafts.value[state.register]
    else drafts.value[state.register] = state.previous
  }
  drag.value = undefined
}
watch([canDrag, () => props.transport], () => {
  selectedRegister.value = null
  drafts.value = {}
  drag.value = undefined
})
function confirm(register: number, value: string) {
  if (drafts.value[register] === Number(value)) delete drafts.value[register]
}
</script>

<template>
  <section class="curve-panel" aria-label="Heizkennlinie">
    <h3>Heizkennlinie</h3>
    <p>
      Außen: {{ valueFor(2048)?.value ?? '—' }} °C · Aktueller Sollwert:
      {{ valueFor(2014)?.value ?? '—' }} °C
    </p>
    <template v-if="line">
      <p class="section-hint">
        {{ mode === 2 ? 'Sieben-Punkt-Kurve' : 'Standardkurve' }}
        <template v-if="canDrag"> · Stützpunkt ziehen und einzeln mit Readback senden.</template>
      </p>
      <svg
        ref="graphic"
        viewBox="0 0 520 250"
        role="group"
        aria-label="Heizsollwert über Außentemperatur"
      >
        <text x="62" y="14">Sollwert (°C)</text>
        <g v-for="tick in yTicks" :key="tick">
          <path :d="'M62 ' + y(tick) + ' H492'" stroke="#dce0e6" />
          <text x="54" :y="y(tick) + 4" text-anchor="end">{{ format.format(tick) }}</text>
        </g>
        <path d="M62 24 V198 H492" fill="none" stroke="#8994a3" />
        <text
          v-for="tick in [-20, -10, 0, 10, 20]"
          :key="tick"
          :x="x(tick)"
          y="219"
          text-anchor="middle"
        >
          {{ tick }}
        </text>
        <text x="492" y="242" text-anchor="end">Außentemperatur (°C)</text>
        <polyline
          :points="line"
          fill="none"
          stroke="#cd641c"
          stroke-width="3"
          stroke-linejoin="round"
        />
        <circle
          v-for="point in markers"
          :key="point.register"
          :cx="x(point.outdoor)"
          :cy="y(point.target)"
          r="5"
          :class="{
            'curve-handle': editable(point.register),
            'curve-selected': selectedRegister === point.register,
          }"
          :tabindex="editable(point.register) ? 0 : undefined"
          :role="editable(point.register) ? 'button' : undefined"
          :aria-label="point.outdoor + ' °C außen, Sollwert ' + format.format(point.target) + ' °C'"
          fill="#cd641c"
          @keydown.enter.prevent="select(point.register)"
          @keydown.space.prevent="select(point.register)"
          @pointerdown="startDrag(point.register, $event)"
          @pointermove="trackDrag"
          @pointerup="stopDrag($event)"
          @pointercancel="stopDrag($event, true)"
          @lostpointercapture="stopDrag($event, true)"
        >
          <title>{{ point.outdoor }} °C außen: {{ format.format(point.target) }} °C Sollwert</title>
        </circle>
      </svg>
    </template>
    <p v-else class="section-hint">
      {{
        mode === 0
          ? 'Heizkennlinie ausgeschaltet.'
          : 'Kurvenwerte oder R10–R11 noch nicht vollständig verfügbar.'
      }}
    </p>
    <template v-if="activePoint && activeRegister && canDrag">
      <h4>Stützpunkt bei {{ activePoint.outdoor }} °C Außentemperatur</h4>
      <ParameterEditor
        :key="activeRegister.register"
        :register="activeRegister"
        :transport="transport"
        :admin="admin"
        :value="valueFor(activeRegister.register)"
        :proposed-value="drafts[activeRegister.register]"
        @updated="emit('updated')"
        @read="emit('updated')"
        @confirmed="confirm(activeRegister.register, $event)"
      />
    </template>
  </section>
</template>

<style scoped>
.curve-handle {
  cursor: ns-resize;
  touch-action: none;
  stroke: transparent;
  stroke-width: 18;
}
.curve-handle:hover,
.curve-handle:focus-visible,
.curve-selected {
  filter: drop-shadow(0 0 2px #964015);
}
</style>
