<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import type { CameraSettings } from '../api'

const props = defineProps<{ available: boolean; mode?: CameraSettings['mode']; interval: number }>()
const cameraStreamUrl = '/api/camera/stream'
const cameraImageUrl = ref('')
let cameraTimer: ReturnType<typeof setTimeout> | undefined
let cameraFrame = 0
const cameraDialog = ref<HTMLDialogElement>()
const cameraOpen = ref(false)
const cameraFailed = ref(false)
function openCamera() {
  if (!props.available || !cameraDialog.value) return
  cameraFailed.value = false
  cameraOpen.value = true
  requestCameraImage()
  cameraDialog.value.showModal()
}
function requestCameraImage() {
  cameraImageUrl.value =
    props.mode === 'jpeg' ? cameraStreamUrl + '?frame=' + ++cameraFrame : cameraStreamUrl
}
function cameraImageSettled(failed: boolean) {
  cameraFailed.value = failed
  clearTimeout(cameraTimer)
  if (cameraOpen.value && props.mode === 'jpeg')
    cameraTimer = setTimeout(requestCameraImage, props.interval)
}
watch(cameraOpen, (opened) => {
  if (!opened) {
    clearTimeout(cameraTimer)
    cameraImageUrl.value = ''
  }
})
function closeCamera() {
  cameraOpen.value = false
  cameraDialog.value?.close()
}
watch(
  () => props.available,
  (available) => {
    if (!available) closeCamera()
  },
)
onBeforeUnmount(() => clearTimeout(cameraTimer))
defineExpose({ open: openCamera })
</script>

<template>
  <dialog
    ref="cameraDialog"
    class="connection-dialog camera-dialog panel"
    aria-labelledby="camera-dialog-title"
    @close="cameraOpen = false"
  >
    <div class="connection-dialog-content">
      <header class="connection-dialog-header">
        <h2 id="camera-dialog-title">Kamerabild der Wärmepumpe</h2>
        <button class="outlined-action" type="button" @click="closeCamera">Schließen</button>
      </header>
      <p v-if="cameraFailed" role="alert">
        Kamerabild nicht verfügbar. Prüfe URL und Bildquelle in den Experteneinstellungen.
      </p>
      <img
        v-if="cameraOpen && cameraImageUrl"
        v-show="!cameraFailed"
        class="heatpump-camera-stream"
        :src="cameraImageUrl"
        alt="Livebild der Wärmepumpe"
        @load="cameraImageSettled(false)"
        @error="cameraImageSettled(true)"
      />
    </div>
  </dialog>
</template>
