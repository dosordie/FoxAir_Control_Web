<script setup lang="ts">
import type { Dashboard, Metric } from '../api'
defineProps<{ metrics?: Dashboard['metrics'] }>()
const fields = [
  { key: 'electrical_power', label: 'Elektrische Leistung', unit: 'kW' },
  { key: 'thermal_power', label: 'Thermische Leistung', unit: 'kW' },
  { key: 'cop', label: 'COP', unit: '' },
] as const
const display = (metric: Metric) =>
  metric?.value == null
    ? '—'
    : typeof metric.value === 'number'
      ? metric.value.toLocaleString('de-DE', { maximumFractionDigits: 2 })
      : metric.value
</script>
<template>
  <div class="power-summary">
    <div
      v-for="field in fields"
      :key="field.key"
      :class="{ 'is-stale': metrics?.[field.key]?.quality === 'stale' }"
    >
      <strong
        >{{ display(metrics?.[field.key] || null) }}
        <small v-if="field.unit">{{ field.unit }}</small></strong
      >
      <small>{{ field.label }}</small>
    </div>
  </div>
</template>
