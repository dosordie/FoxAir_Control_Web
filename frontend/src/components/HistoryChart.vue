<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { HistoryPoint } from '../api'

const props = defineProps<{
  points: HistoryPoint[]
  label: string
  unit: string
  step?: number
  cloud?: boolean
}>()
const selected = ref<number | null>(null)
const tooltip = ref(false)
const pointer = ref<{ x: number; y: number } | null>(null)
const plot = { left: 72, right: 570, top: 15, bottom: 147 }
const tickFormat = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 })
const model = computed(() => {
  const points = props.points
    .flatMap((point) => {
      const stamp =
        props.cloud && !/(?:Z|[+-]\d\d:?\d\d)$/i.test(point.time)
          ? point.time.replace(' ', 'T') + '+01:00'
          : point.time
      const time = Date.parse(stamp)
      return Number.isFinite(time) && Number.isFinite(point.value) ? [{ ...point, time }] : []
    })
    .sort((a, b) => a.time - b.time)
  if (!points.length) return null
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const padding = min === max ? Math.max(0.5, Math.abs(min) * 0.05) : (max - min) * 0.05
  const low = min - padding
  const high = max + padding
  const first = points[0]!.time
  const span = points[points.length - 1]!.time - first
  const coordinates = points.map((point) => ({
    ...point,
    x: span
      ? plot.left + ((point.time - first) / span) * (plot.right - plot.left)
      : (plot.left + plot.right) / 2,
    y: plot.bottom - ((point.value - low) / (high - low)) * (plot.bottom - plot.top),
  }))
  const segments: string[] = []
  for (const [index, point] of coordinates.entries()) {
    const previous = coordinates[index - 1]
    const gap = !previous || (props.step && point.time - previous.time > props.step * 1500)
    segments.push(`${gap ? 'M' : 'L'}${point.x},${point.y}`)
  }
  return { coordinates, path: segments.join(' '), first, span, low, high }
})
watch(model, () => {
  selected.value = null
  tooltip.value = false
  pointer.value = null
})
const active = computed(() =>
  selected.value === null ? null : model.value?.coordinates[selected.value],
)
const tipPosition = computed(() => {
  const point = active.value
  if (!point) return null
  return pointer.value ?? { x: point.x / 6, y: (point.y / 179) * 100 }
})
const clock = (time: number, detail = false) =>
  new Intl.DateTimeFormat('de-DE', {
    ...(props.cloud ? { timeZone: 'Etc/GMT-1' } : {}),
    ...(detail || (model.value?.span ?? 0) > 86400000 ? { day: '2-digit', month: '2-digit' } : {}),
    ...(detail || (model.value?.span ?? 0) <= 86400000
      ? { hour: '2-digit', minute: '2-digit' }
      : {}),
  }).format(time)

function selectPoint(event: PointerEvent) {
  if (!model.value) return
  if (event.type === 'pointermove' && event.pointerType === 'touch') return
  const bounds = (event.currentTarget as SVGElement).getBoundingClientRect()
  if (!bounds.width) return
  const x = ((event.clientX - bounds.left) / bounds.width) * 600
  let closest = 0
  for (const [index, point] of model.value.coordinates.entries()) {
    if (Math.abs(point.x - x) < Math.abs(model.value.coordinates[closest]!.x - x)) closest = index
  }
  selected.value = closest
  pointer.value =
    event.pointerType === 'touch'
      ? null
      : {
          x: Math.max(0, Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100)),
          y: Math.max(0, Math.min(100, ((event.clientY - bounds.top) / bounds.height) * 100)),
        }
  tooltip.value = true
}
function navigate(direction: number) {
  pointer.value = null
  tooltip.value = true
  if (model.value)
    selected.value = Math.min(
      model.value.coordinates.length - 1,
      Math.max(0, (selected.value ?? -1) + direction),
    )
}
</script>

<template>
  <figure v-if="model" class="measurement-chart">
    <figcaption>
      {{ label }}<template v-if="unit"> ({{ unit }})</template> · Zeit<template v-if="cloud">
        (UTC+1)</template
      >
    </figcaption>
    <div class="history-plot">
      <svg
        viewBox="0 0 600 179"
        class="history-chart"
        role="group"
        :aria-label="'Diagramm: ' + label"
        tabindex="0"
        @pointermove="selectPoint"
        @pointerup="selectPoint"
        @pointerleave="
          (event) => {
            if (event.pointerType !== 'touch') tooltip = false
          }
        "
        @blur="tooltip = false"
        @keydown.left.prevent="navigate(-1)"
        @keydown.right.prevent="navigate(1)"
      >
        <g v-for="index in 5" :key="index">
          <line
            :x1="plot.left"
            :x2="plot.right"
            :y1="plot.top + ((index - 1) / 4) * (plot.bottom - plot.top)"
            :y2="plot.top + ((index - 1) / 4) * (plot.bottom - plot.top)"
            stroke="#d7dce3"
          />
          <text
            :x="plot.left - 8"
            :y="plot.top + ((index - 1) / 4) * (plot.bottom - plot.top) + 5"
            text-anchor="end"
          >
            {{ tickFormat.format(model.high - ((index - 1) / 4) * (model.high - model.low)) }}
          </text>
        </g>
        <path
          :d="`M${plot.left} ${plot.top}V${plot.bottom}H${plot.right}`"
          fill="none"
          stroke="#727b8a"
        />
        <text
          v-for="tick in model.span ? [0, 0.5, 1] : [0.5]"
          :key="tick"
          :x="plot.left + tick * (plot.right - plot.left)"
          y="171"
          text-anchor="middle"
        >
          {{ clock(model.first + model.span * tick) }}
        </text>
        <path :d="model.path" fill="none" stroke="#d76b21" stroke-width="3" />
        <circle
          v-for="point in model.coordinates.length <= 80 ? model.coordinates : []"
          :key="point.time"
          :cx="point.x"
          :cy="point.y"
          r="2.8"
          fill="#d76b21"
        />
        <g v-if="active">
          <line
            :x1="active.x"
            :x2="active.x"
            :y1="plot.top"
            :y2="plot.bottom"
            stroke="#727b8a"
            stroke-dasharray="4 4"
          />
          <circle :cx="active.x" :cy="active.y" r="5" fill="#d76b21" />
        </g>
      </svg>
      <div
        v-if="active && tooltip && tipPosition"
        class="history-tooltip"
        aria-hidden="true"
        :class="{ 'tip-left': tipPosition.x >= 52, 'tip-below': tipPosition.y < 32 }"
        :style="{ left: tipPosition.x + '%', top: tipPosition.y + '%' }"
      >
        <span>{{ clock(active.time, true) }}</span>
        <strong>{{ tickFormat.format(active.value) }} {{ unit }}</strong>
      </div>
    </div>
    <p v-if="active" class="section-hint" role="status">
      {{ clock(active.time, true) }} · {{ tickFormat.format(active.value) }} {{ unit }}
    </p>
  </figure>
</template>
