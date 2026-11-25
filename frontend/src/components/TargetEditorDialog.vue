<script setup lang="ts">
import { ref, watch } from 'vue'
import { api, type Register, type RegisterValue, type TransportId } from '../api'
import ParameterEditor from './ParameterEditor.vue'

const props = defineProps<{
  canEdit: boolean
  transport: TransportId
  effectiveTarget: string
  currentValue: RegisterValue | null
}>()
const emit = defineEmits<{ updated: [] }>()

const targetEditor = ref<HTMLDialogElement | null>(null)
const targetDefinition = ref<Register | null>(null)
const targetError = ref('')
const targetLoading = ref(false)
async function openTargetEditor() {
  if (!props.canEdit) return
  targetEditor.value?.showModal()
  targetError.value = ''
  if (targetDefinition.value) return
  targetLoading.value = true
  try {
    targetDefinition.value =
      (await api.registers('1158')).items.find((item) => item.register === 1158) ?? null
    if (!targetDefinition.value) targetError.value = 'Heizungs-Basissollwert nicht verfügbar.'
  } catch (cause) {
    targetError.value = (cause as Error).message
  } finally {
    targetLoading.value = false
  }
}
watch([() => props.canEdit, () => props.transport], () => targetEditor.value?.close())
defineExpose({ open: openTargetEditor })
</script>

<template>
  <dialog ref="targetEditor" class="operation-dialog panel" aria-labelledby="target-editor-title">
    <div class="special-top">
      <h2 id="target-editor-title">Heizungs-Basissollwert</h2>
      <button type="button" class="outlined-action" @click="targetEditor?.close()">
        Schließen
      </button>
    </div>
    <p>Aktuell wirksamer Sollwert: {{ effectiveTarget }}</p>
    <p class="section-hint">
      Die Heizkurve kann den wirksamen Sollwert gegenüber dem eingestellten Basiswert verändern.
    </p>
    <p v-if="targetLoading" role="status">Parameter wird geladen …</p>
    <p v-if="targetError" class="read-error" role="alert">{{ targetError }}</p>
    <ParameterEditor
      v-if="targetDefinition && canEdit"
      :key="transport"
      :register="targetDefinition"
      :transport="transport"
      :admin="canEdit"
      :value="currentValue"
      @updated="emit('updated')"
    />
  </dialog>
</template>
