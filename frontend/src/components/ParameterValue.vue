<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(
  defineProps<{
    value: string | number | null | undefined
    unit?: string
    timestamp?: string | null
    label?: string
    quality?: string
  }>(),
  { unit: '', label: 'Aktueller Wert' },
)
const text = computed(() => (props.value == null || props.value === '' ? '—' : String(props.value)))
const longText = computed(
  () => text.value.length > 12 && !/^[+-]?\d+(?:[.,]\d+)?$/.test(text.value),
)
const timestampText = computed(() =>
  props.timestamp ? new Date(props.timestamp).toLocaleString('de-DE') : 'Noch kein Messwert',
)
</script>

<template>
  <div class="detail-value" :class="{ 'text-value': longText, 'is-stale': quality === 'stale' }">
    <span>{{ label }}</span>
    <strong
      >{{ text }} <small v-if="unit">{{ unit }}</small></strong
    >
    <p>{{ timestampText }}<template v-if="quality === 'stale'"> · veraltet</template></p>
  </div>
</template>
