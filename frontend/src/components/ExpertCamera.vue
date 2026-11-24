<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const emit = defineEmits<{ saved: [enabled: boolean] }>()
const enabled = ref(false)
const url = ref('')
const busy = ref(true)
const loaded = ref(false)
const error = ref('')
const saved = ref(false)

onMounted(async () => {
  try {
    const settings = await api.cameraSettings()
    enabled.value = settings.enabled
    url.value = settings.url
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
    const settings = await api.saveCamera({ enabled: enabled.value, url: url.value })
    url.value = settings.url
    emit('saved', settings.enabled)
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
    <summary>Experteneinstellungen · Wärmepumpenkamera</summary>
    <form v-if="loaded" @submit.prevent="save">
      <label class="settings-check"
        ><input v-model="enabled" type="checkbox" /> Kamera aktivieren</label
      >
      <label class="field-label" for="camera-url">MJPEG-Stream-URL</label>
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
