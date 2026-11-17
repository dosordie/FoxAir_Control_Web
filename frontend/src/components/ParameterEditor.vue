<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { api, type Register, type RegisterValue, type TransportId } from '../api'

const props = defineProps<{
  register: Register
  transport: TransportId
  admin: boolean
  value?: RegisterValue | null
}>()
const emit = defineEmits<{ updated: []; read: [RegisterValue] }>()
const baseline = ref<RegisterValue | null>(null)
const draft = ref<string | number>('')
const busy = ref(false)
const error = ref('')
const message = ref('')
const dirty = ref(false)
let generation = 0
let disposed = false
function acceptValue(row: RegisterValue | null | undefined) {
  if (
    !row ||
    row.register !== props.register.register ||
    row.value == null ||
    row.value === '' ||
    !['cloud', 'warmlink_raw', 'standard_modbus'].includes(row.transport) ||
    !['fresh', 'cached', 'observed', 'stale'].includes(row.quality) ||
    !Number.isFinite(Date.parse(row.timestamp))
  )
    return
  const raw = row.raw
  if (
    row.transport === 'cloud'
      ? !Number.isFinite(Number(String(row.value).replace(',', '.')))
      : raw == null || !Number.isInteger(raw) || raw < 0 || raw > 65535
  )
    return
  baseline.value = row
  let editable =
    row.edit_value ??
    (Object.keys(props.register.value_map).length && raw !== null ? String(raw) : row.value)
  if (row.edit_value == null && row.transport === 'cloud') {
    const word = Number(row.value)
    if (props.register.type.toUpperCase() === 'TIME_HHMM' && Number.isInteger(word))
      editable = String(word >> 8).padStart(2, '0') + ':' + String(word & 255).padStart(2, '0')
    if (
      props.register.type.toUpperCase() === 'TIMER_BITPAIR' &&
      /^[01]{16}$/.test(String(row.value))
    )
      editable = parseInt(String(row.value), 2)
  }
  draft.value = editable
}
watch(
  () => props.value,
  (row) => {
    if (!dirty.value && !busy.value) acceptValue(row)
  },
  { immediate: true },
)
watch(
  () => props.admin,
  () => {
    generation++
    baseline.value = null
    dirty.value = false
    busy.value = false
    acceptValue(props.value)
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
    dirty.value = false
    acceptValue(row)
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
    const expected = row.transport === 'cloud' ? row.value : row.raw
    const result = await api.writeParameter(
      props.register.register,
      props.transport,
      String(draft.value),
      String(expected),
      row.transport,
    )
    if (disposed || current !== generation) return
    baseline.value = null
    dirty.value = false
    message.value = result.confirmed
      ? result.status === 'unchanged'
        ? 'Wert unverändert; kein Schreibbefehl nötig.'
        : 'Wert per Readback bestätigt.'
      : result.message || 'Readback abweichend. Aktuellen Zustand neu lesen.'
    emit('updated')
  } catch (failure) {
    if (!disposed && current === generation) {
      baseline.value = null
      dirty.value = false
      error.value = failure instanceof Error ? failure.message : 'Schreibauftrag fehlgeschlagen'
      emit('updated')
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
    <p class="section-hint">
      Wert ändern und mit Readback senden. Der Ausgangswert wird vor dem Senden automatisch geprüft.
    </p>
    <button type="button" class="outlined-action" :disabled="busy" @click="readBaseline">
      Wert aktualisieren
    </button>
    <template v-if="baseline">
      <label class="field-label" for="parameter-draft">Neuer Wert {{ register.unit }}</label>
      <select
        v-if="Object.keys(register.value_map).length"
        id="parameter-draft"
        class="settings-input"
        v-model="draft"
        :disabled="busy"
        @input="dirty = true"
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
        @input="dirty = true"
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
