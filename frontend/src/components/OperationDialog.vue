<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, writeValueText, type CloudRow, type RegisterValue, type TransportId } from '../api'

const props = defineProps<{
  transport: TransportId
  transportLabel: string
  cloudRows: CloudRow[]
  admin: boolean
  canOperate: boolean
  cachedValue?: (register: number) => RegisterValue | null
}>()
const emit = defineEmits<{ updated: []; refreshCloud: [] }>()

const controls = {
  Power: { register: 1011, label: 'Ein / Aus' },
  Mode: { register: 1012, label: 'Betriebsart' },
  H22: { register: 1030, label: 'Ruhemodus' },
}
type ControlCode = keyof typeof controls
const modes = ['Warmwasser', 'Heizen', 'Kühlen', 'Warmwasser + Heizen', 'Warmwasser + Kühlen']
const binaryOptions = ['Aus', 'Ein']
const dialog = ref<HTMLDialogElement>()
const code = ref<ControlCode | null>(null)
const source = ref<RegisterValue | null>(null)
const draft = ref('')
const reading = ref(false)
const writing = ref(false)
const error = ref('')
const feedback = ref('')
let generation = 0

const current = computed(
  () =>
    source.value ??
    (props.transport === 'cloud'
      ? (props.cloudRows.find((row) => row.code === code.value) ?? null)
      : props.transport === 'display_modbus' && code.value
        ? (props.cachedValue?.(controls[code.value].register) ?? null)
        : null),
)
const options = computed(() => (code.value === 'Mode' ? modes : binaryOptions))
const label = computed(() => {
  const value = String(current.value?.value ?? '—')
  return options.value[Number(value)] ?? value
})
const canWrite = computed(() => {
  const row = current.value
  return (
    props.canOperate &&
    !writing.value &&
    !reading.value &&
    ['cloud', 'warmlink_raw', 'standard_modbus'].includes(props.transport) &&
    !!row &&
    row.value !== null &&
    ['fresh', 'cached'].includes(row.quality)
  )
})

function reset() {
  generation++
  code.value = null
  source.value = null
  reading.value = false
}
function close() {
  reset()
  dialog.value?.close()
}
async function refresh() {
  const control = code.value
  if (!control) return
  const request = ++generation
  const transport = props.transport
  reading.value = true
  error.value = ''
  try {
    const row = await api.read(controls[control].register, transport)
    if (request !== generation || transport !== props.transport) return
    const rawValue = transport === 'cloud' ? row.value : (row.raw ?? row.value)
    const value = Number.isFinite(Number(rawValue)) ? Number(rawValue) : rawValue
    source.value = { ...row, value }
    draft.value = String(value)
  } catch (cause) {
    if (request === generation && !(transport === 'display_modbus' && current.value))
      error.value = cause instanceof Error ? cause.message : 'Lesen fehlgeschlagen'
  } finally {
    if (request === generation) reading.value = false
  }
}
function open(control: ControlCode) {
  if (!dialog.value || dialog.value.open) return
  code.value = control
  draft.value = String(current.value?.value ?? '')
  error.value = ''
  feedback.value = ''
  dialog.value.showModal()
  void refresh()
}
async function submit() {
  const control = code.value
  const row = current.value
  const desired = writeValueText(draft.value)
  const transport = props.transport
  if (!control || !row || !desired || !canWrite.value) return
  const request = generation
  if (
    transport === 'standard_modbus' &&
    (!('raw' in row) || row.raw == null || row.transport !== transport)
  )
    return
  writing.value = true
  feedback.value = ''
  error.value = ''
  const isLte = transport === 'warmlink_raw'
  try {
    const result =
      transport === 'standard_modbus' && 'raw' in row
        ? await api.writeParameter(
            controls[control].register,
            transport,
            desired,
            String(row.raw),
            transport,
          )
        : await (isLte ? api.warmlinkWrite : api.cloudWrite)(control, desired, String(row.value))
    if (request === generation) {
      const readback = generation + 1
      await refresh()
      if (readback === generation && props.transport === transport) {
        if (result.confirmed) {
          const connection =
            transport === 'standard_modbus' ? 'Standard-Modbus' : isLte ? 'LTE' : 'Cloud'
          feedback.value =
            result.status === 'unchanged'
              ? 'Wert ist bereits eingestellt.'
              : controls[control].label + ' wurde durch ' + connection + '-Readback bestätigt.'
        } else {
          error.value = result.message || 'Schreiben nicht bestätigt; bitte Wert kontrollieren.'
        }
      }
    } else if (transport === 'cloud') {
      emit('refreshCloud')
    }
    emit('updated')
  } catch (cause) {
    if (request === generation)
      error.value = cause instanceof Error ? cause.message : 'Schreiben fehlgeschlagen'
    emit('refreshCloud')
  } finally {
    writing.value = false
  }
}

watch(() => props.transport, close)
defineExpose({ open })
</script>

<template>
  <dialog
    ref="dialog"
    class="operation-dialog panel"
    aria-labelledby="operation-title"
    @close="reset"
  >
    <div class="special-top">
      <h2 id="operation-title">{{ code ? controls[code].label : '' }}</h2>
      <button
        class="outlined-action"
        type="button"
        aria-label="Betriebsdialog schließen"
        @click="close"
      >
        Schließen
      </button>
    </div>
    <template v-if="code">
      <p class="section-hint">{{ transportLabel }} · Aktueller Wert: {{ label }}</p>
      <p v-if="transport === 'display_modbus' && !source && current" class="section-hint">
        Letzter gespeicherter Wert · {{ new Date(current.timestamp!).toLocaleString('de-DE') }}
      </p>
      <button class="outlined-action" type="button" :disabled="reading || writing" @click="refresh">
        Wert aktualisieren
      </button>
      <label class="field-label" for="operation-value">Neuer Wert</label>
      <select
        id="operation-value"
        v-model="draft"
        class="settings-input"
        :disabled="writing || reading"
      >
        <option v-for="(option, value) in options" :key="option" :value="String(value)">
          {{ option }}
        </option>
      </select>
      <p v-if="error" class="read-error" role="alert">{{ error }}</p>
      <p v-if="feedback" class="success-text" role="status">{{ feedback }}</p>
      <p v-if="!admin" class="section-hint">Zum Ändern oben rechts als Administrator anmelden.</p>
      <button class="main-action" type="button" :disabled="!canWrite" @click="submit">
        {{ writing ? 'Prüfe und schreibe …' : 'Wert mit Readback senden' }}
      </button>
    </template>
  </dialog>
</template>
