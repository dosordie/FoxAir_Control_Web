<script setup lang="ts">
import { RefreshCw } from 'lucide-vue-next'
import type { LteScan } from '../api'
defineProps<{ scan: LteScan; valueCount: number; connected: boolean; starting: boolean }>()
defineEmits<{ refresh: [] }>()
</script>

<template>
  <section class="lte-summary" aria-label="LTE-Parameterstatus">
    <div class="lte-summary-info" role="status">
      <strong>LTE · {{ scan.completed }}/{{ scan.total }} Blöcke</strong>
      <span>{{ valueCount }} Werte · {{ connected ? 'Live' : 'Verbinde …' }}</span>
    </div>
    <button
      type="button"
      class="filter-icon"
      aria-label="Alle LTE-Register aktualisieren"
      title="Alle LTE-Register aktualisieren"
      :disabled="starting || scan.status === 'running'"
      @click="$emit('refresh')"
    >
      <RefreshCw :size="18" :class="{ spinning: starting || scan.status === 'running' }" />
    </button>
    <progress
      v-if="scan.status === 'running'"
      :value="scan.completed"
      :max="scan.total"
      aria-label="Fortschritt der LTE-Blockabfrage"
    />
    <p v-if="scan.error" role="alert" class="read-error">{{ scan.error }}</p>
  </section>
</template>
