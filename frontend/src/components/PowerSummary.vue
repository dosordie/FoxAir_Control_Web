<script setup lang="ts">
import { computed } from 'vue'
import type { Dashboard, GiraItem } from '../api'
import { giraIcon } from '../giraIcons'
import { overviewFields, type OverviewField } from '../overview'

const props = defineProps<{
  metrics?: Dashboard['metrics']
  selection: string[]
  gira: GiraItem[]
  spread: number | null
}>()
const format = (value: string | number | null | undefined) =>
  typeof value === 'number'
    ? value.toLocaleString('de-DE', { maximumFractionDigits: 2 })
    : (value ?? '—')

const fields = computed(() =>
  props.selection.flatMap((key) => {
    if (key.startsWith('gira:') && !props.selection.includes('gira')) {
      const item = props.gira.find((entry) => entry.layout_key === key)
      return [
        {
          key,
          label: item?.name || '',
          icon: giraIcon(item?.icon),
          unit: item?.unit || '',
          text: format(item?.value),
          stale: item?.quality === 'stale',
        },
      ]
    }
    if (!Object.hasOwn(overviewFields, key)) return []
    const field = overviewFields[key as OverviewField]
    const item = key === 'spread' ? null : props.metrics?.[key as keyof Dashboard['metrics']]
    return [
      {
        key,
        ...field,
        text: format(key === 'spread' ? props.spread : item?.value),
        stale:
          item?.quality === 'stale' ||
          (key === 'spread' &&
            (props.metrics?.supply?.quality === 'stale' ||
              props.metrics?.return?.quality === 'stale')),
      },
    ]
  }),
)
</script>

<template>
  <div v-if="fields.length" class="power-summary">
    <div v-for="field in fields" :key="field.key" :class="{ 'is-stale': field.stale }">
      <component :is="field.icon" :size="17" aria-hidden="true" />
      <strong
        >{{ field.text }} <small v-if="field.unit">{{ field.unit }}</small></strong
      >
      <small v-if="field.label">{{ field.label }}</small>
    </div>
  </div>
</template>
