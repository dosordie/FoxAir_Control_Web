<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, type HistorySeries, type HistorySettings } from '../api'
import HistoryChart from './HistoryChart.vue'

defineProps<{ settings?: boolean }>()
const config = ref<HistorySettings | null>(null)
const series = ref<HistorySeries | null>(null)
const defrost = ref<{ start: string; duration_seconds: number }[] | null>(null)
const duration = (seconds: number) => Math.floor(seconds / 60) + ' min ' + (seconds % 60) + ' s'
const selected = ref(2046)
const days = ref(1)
const enabled = ref(false)
const retention = ref(90)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const periods = computed(() =>
  [...new Set([1, 7, 30, 90, config.value?.retention_days ?? 90])]
    .filter((period) => period <= (config.value?.retention_days ?? 90))
    .sort((a, b) => a - b),
)

function apply(data: HistorySettings) {
  config.value = data
  enabled.value = data.enabled
  retention.value = data.retention_days
}

onMounted(async () => {
  try {
    const data = await api.historySettings()
    if (Array.isArray(data.fields)) apply(data)
  } catch (cause) {
    error.value = (cause as Error).message
  }
})

async function save() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    apply(await api.saveHistorySettings(enabled.value, retention.value))
    notice.value = 'Verlaufseinstellungen gespeichert.'
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}

async function load() {
  busy.value = true
  error.value = ''
  series.value = null
  defrost.value = null
  try {
    if (selected.value === 2012) defrost.value = (await api.defrostHistory(days.value)).events
    else series.value = await api.localHistory(selected.value, days.value)
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="settings-panel panel">
    <h2>Lokaler Verlauf</h2>
    <form v-if="config && settings" @submit.prevent="save">
      <label class="settings-check"
        ><input v-model="enabled" type="checkbox" /> Messwerte aufzeichnen</label
      >
      <label class="field-label" for="history-retention">Aufbewahrung in Tagen</label>
      <input
        id="history-retention"
        v-model.number="retention"
        class="settings-input"
        type="number"
        min="1"
        max="365"
        required
      />
      <p class="section-hint">
        FoxAir fasst empfangene Messwerte in 5-Minuten-Intervallen zusammen und speichert sie alle
        15 Minuten gesammelt. Für einen lückenlosen Verlauf braucht FoxAir eine dauerhaft
        eingestellte Verbindung. Ohne laufenden Empfang entstehen Lücken. Die Aufzeichnung ändert
        die Verbindungseinstellung nicht.
      </p>
      <button type="submit" class="outlined-action" :disabled="busy">
        Verlaufseinstellungen speichern
      </button>
    </form>
    <form v-else-if="config" class="cloud-extra-controls" @submit.prevent="load">
      <label
        >Messwert<select v-model.number="selected" class="settings-input">
          <option v-for="field in config.fields" :key="field.register" :value="field.register">
            {{ field.label }}
          </option>
          <option :value="2012">Abtauvorgänge</option>
        </select></label
      >
      <label
        >Zeitraum<select v-model.number="days" class="settings-input">
          <option v-for="period in periods" :key="period" :value="period">
            {{ period === 1 ? '24 Stunden' : period + ' Tage' }}
          </option>
        </select></label
      >
      <button type="submit" class="outlined-action" :disabled="busy">Verlauf laden</button>
    </form>
    <p v-if="config && !settings && !config.enabled" class="section-hint">
      Die lokale Aufzeichnung ist ausgeschaltet. Gespeicherte Daten bleiben bis zum Ende ihrer
      Aufbewahrungszeit abrufbar.
    </p>
    <template v-if="defrost">
      <h3>Abtauvorgänge</h3>
      <div v-if="defrost.length" class="history-points">
        <div v-for="(event, index) in defrost" :key="event.start + ':' + index">
          <time :datetime="event.start">{{ new Date(event.start).toLocaleString('de-DE') }}</time>
          <strong>{{ duration(event.duration_seconds) }}</strong>
        </div>
      </div>
      <p v-else>Für diesen Zeitraum sind keine vollständigen Abtauvorgänge aufgezeichnet.</p>
    </template>
    <template v-if="series">
      <HistoryChart
        v-if="series.points.length"
        :points="series.points"
        :label="series.label"
        :unit="series.unit"
        :step="series.step_seconds"
      />
      <p v-else>Für diesen Zeitraum sind keine Messwerte gespeichert.</p>
    </template>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="error" class="read-error" role="alert">{{ error }}</p>
  </section>
</template>
