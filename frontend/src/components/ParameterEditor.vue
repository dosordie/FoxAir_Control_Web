<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { api, type Register, type RegisterValue, type TransportId } from '../api'

const props = defineProps<{ register: Register; transport: TransportId; admin: boolean }>()
const emit = defineEmits<{ updated: []; read: [RegisterValue] }>()
const baseline = ref<RegisterValue | null>(null)
const draft = ref<string | number>('')
const busy = ref(false)
const error = ref('')
const message = ref('')
let generation = 0
let disposed = false
watch(
  () => props.admin,
  () => {
    generation++
    baseline.value = null
    busy.value = false
  },
)
onBeforeUnmount(() => {
  disposed = true
  generation++
})

async function readBaseline() {
  const current = ++generation
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    const row = await api.read(props.register.register, props.transport)
    if (disposed || current !== generation) return
    baseline.value = row
    draft.value =
      row.edit_value ??
      (Object.keys(props.register.value_map).length && row.raw !== null
        ? String(row.raw)
        : row.value)
    message.value = 'Ausgangswert frisch gelesen.'
    emit('read', row)
  } catch (failure) {
    if (!disposed && current === generation)
      error.value = failure instanceof Error ? failure.message : 'Lesefehler'
  } finally {
    if (!disposed && current === generation) busy.value = false
  }
}
async function submit() {
  const row = baseline.value
  if (!props.admin || !row || busy.value) return
  const current = ++generation
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    const expected = props.transport === 'cloud' ? row.value : row.raw
    const result = await api.writeParameter(
      props.register.register,
      props.transport,
      String(draft.value),
      String(expected),
    )
    if (disposed || current !== generation) return
    baseline.value = null
    message.value = result.confirmed
      ? result.status === 'unchanged'
        ? 'Wert unverändert; kein Schreibbefehl nötig.'
        : 'Wert per Readback bestätigt.'
      : result.message || 'Readback abweichend. Aktuellen Zustand neu lesen.'
    emit('updated')
  } catch (failure) {
    if (!disposed && current === generation) {
      baseline.value = null
      error.value = failure instanceof Error ? failure.message : 'Schreibauftrag fehlgeschlagen'
    }
  } finally {
    if (!disposed && current === generation) busy.value = false
  }
}
</script>

<template>
  <section
    v-if="
      register.write_available && ['cloud', 'warmlink_raw', 'standard_modbus'].includes(transport)
    "
    class="cloud-write-panel"
  >
    <strong>Parameter bearbeiten</strong>
    <p class="section-hint">Ausgangswert lesen, Wert ändern und mit Readback senden.</p>
    <button type="button" class="outlined-action" :disabled="busy" @click="readBaseline">
      Ausgangswert lesen
    </button>
    <template v-if="baseline">
      <label class="field-label" for="parameter-draft">Neuer Wert {{ register.unit }}</label>
      <select
        v-if="Object.keys(register.value_map).length"
        id="parameter-draft"
        class="settings-input"
        v-model="draft"
        :disabled="busy"
      >
        <option v-for="(label, value) in register.value_map" :key="value" :value="value">
          {{ label }} ({{ value }})
        </option>
      </select>
      <input
        v-else
        id="parameter-draft"
        class="settings-input"
        v-model="draft"
        :disabled="busy"
        :type="register.type.toUpperCase() === 'TIME_HHMM' ? 'text' : 'number'"
        step="any"
      />
      <button
        type="button"
        class="main-action"
        :disabled="!admin || busy || draft === ''"
        @click="submit"
      >
        {{ busy ? 'Prüfe und schreibe …' : 'Wert mit Readback senden' }}
      </button>
    </template>
    <p v-if="!admin" class="section-hint">Zum Schreiben als Administrator anmelden.</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error" class="read-error" role="alert">{{ error }}</p>
  </section>
  <p v-else class="section-hint">Dieser Parameter ist laut Quellkatalog nur lesbar.</p>
</template>
