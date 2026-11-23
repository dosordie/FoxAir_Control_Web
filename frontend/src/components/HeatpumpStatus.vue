<script setup lang="ts">
import { computed } from 'vue'
import { Snowflake, Droplets, Sun } from 'lucide-vue-next'
import { heatpumpState } from '../telemetry'
import type { Metric, RegisterValue } from '../api'
const props = defineProps<{
  mode: RegisterValue | null
  run: RegisterValue | null
  power: Metric
}>()
const state = computed(() => heatpumpState(props.mode, props.run, props.power))
</script>
<template>
  <div class="heatpump-status-icons" aria-label="Betriebssymbole">
    <span
      v-if="state.defrost"
      class="heatpump-state defrost-state"
      role="img"
      aria-label="Abtauen"
      title="Abtauen"
    >
      <Snowflake :size="23" class="status-primary" /><Droplets :size="15" class="status-drop" />
    </span>
    <span
      v-if="state.label"
      class="heatpump-state mode-state"
      role="img"
      :aria-label="state.label"
      :title="state.label"
    >
      <Sun v-if="state.heating" :size="23" class="status-primary" />
      <Snowflake v-if="state.cooling" :size="23" />
      <Droplets
        v-if="state.water"
        :size="state.heating || state.cooling ? 16 : 23"
        :class="{ 'status-drop': state.heating || state.cooling }"
      />
    </span>
  </div>
</template>
