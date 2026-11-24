<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type CameraSettings } from '../api'

const emit = defineEmits<{ saved: [settings: CameraSettings] }>()
const enabled = ref(false)
const url = ref('')
const mode = ref<CameraSettings['mode']>('mjpeg')
const interval = ref(2000)
const busy = ref(true)
const loaded = ref(false)
const error = ref('')
const saved = ref(false)

onMounted(async () => {
  try {
    const settings = await api.cameraSettings()
    enabled.value = settings.enabled
    url.value = settings.url
    mode.value = settings.mode
    interval.value = settings.interval_ms
    loaded.value = true
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
})

async function save() {
  busy.value = true
  saved.value = false
  error.value = ''
  try {
    const settings = await api.saveCamera({
      enabled: enabled.value,
      url: url.value,
      mode: mode.value,
      interval_ms: interval.value,
    })
    url.value = settings.url
    emit('saved', settings)
    saved.value = true
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <details class="settings-panel panel">
    <summary>Kamera</summary>
    <form v-if="loaded" @submit.prevent="save">
      <label class="settings-check"
        ><input v-model="enabled" type="checkbox" /> Kamera aktivieren</label
      >
      <label class="field-label" for="camera-mode">Bildquelle</label>
      <select id="camera-mode" v-model="mode" class="settings-input">
        <option value="jpeg">JPEG · Einzelbild</option>
        <option value="mjpeg">MJPEG · Livestream</option>
      </select>
      <template v-if="mode === 'jpeg'">
        <label class="field-label" for="camera-interval">Abrufintervall in Millisekunden</label>
        <input
          id="camera-interval"
          v-model.number="interval"
          class="settings-input"
          type="number"
          min="200"
          max="60000"
          step="1"
          required
        />
      </template>
      <label class="field-label" for="camera-url">Kamera-URL</label>
      <input
        id="camera-url"
        v-model.trim="url"
        class="settings-input"
        type="url"
        :required="enabled"
        maxlength="2048"
      />
      <p class="section-hint">
        Die Kamera muss für den FoxAir-Webserver im privaten Netz erreichbar sein. Das Livebild ist
        für angemeldete Benutzer sichtbar.
      </p>
      <button class="outlined-action" type="submit" :disabled="busy">Kamera speichern</button>
    </form>
    <p v-if="saved" role="status">Kameraeinstellungen gespeichert.</p>
    <p v-if="error" class="read-error" role="alert">{{ error }}</p>
  </details>
</template>
