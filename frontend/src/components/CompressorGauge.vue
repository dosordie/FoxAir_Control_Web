<script setup lang="ts">
import { computed } from 'vue'
import type { Metric } from '../api'
const props = defineProps<{ metric: Metric }>()
const frequency = computed(() => {
  const value = props.metric?.value
  const hz = value == null || value === '' ? NaN : Number(value)
  if (!Number.isFinite(hz)) return null
  return {
    hz,
    percent: Math.max(0, Math.min(100, ((hz - 28) / 62) * 100)),
    color: hz <= 38 ? '#349f55' : hz <= 50 ? '#e88a20' : hz <= 70 ? '#d24b4b' : '#8755bb',
  }
})
</script>
<template>
  <span
    class="compressor-hz"
    :class="{ 'is-stale': metric?.quality === 'stale' }"
    aria-label="Kompressor-Istfrequenz"
    >{{ frequency?.hz ?? '—' }} Hz</span
  >
  <div
    class="compressor-gauge"
    :class="{ 'is-stale': metric?.quality === 'stale' }"
    role="meter"
    aria-label="Kompressorfrequenz zwischen 28 und 90 Hz"
    :aria-valuenow="frequency?.percent"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-valuetext="frequency ? frequency.hz + ' Hz' : 'Kein Messwert'"
  >
    <div class="compressor-track">
      <div
        class="compressor-fill"
        :style="{ width: (frequency?.percent || 0) + '%', background: frequency?.color }"
      ></div>
    </div>
    <small>{{ frequency ? Math.round(frequency.percent) + ' %' : '—' }} · 28–90 Hz</small>
  </div>
</template>
