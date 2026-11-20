<script setup lang="ts">
import { computed, onMounted, ref, watch, nextTick } from 'vue'
const emit = defineEmits<{ completed: [] }>()
const modal = ref<HTMLDialogElement | null>(null)
const lanHttp = ref(false)
const secure = computed(
  () =>
    lanHttp.value ||
    window.location.protocol === 'https:' ||
    ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname),
)
const required = ref(false),
  container = ref(false),
  code = ref(''),
  password = ref(''),
  repeat = ref(''),
  busy = ref(false),
  error = ref('')
watch(
  () => required.value,
  async (value) => {
    await nextTick()
    if (value && modal.value && !modal.value.open) modal.value.showModal()
  },
)
onMounted(async () => {
  try {
    const response = await fetch('/api/setup/status')
    if (response.ok) {
      const data = await response.json()
      required.value = data.required
      container.value = data.container
      lanHttp.value = data.lan_http === true
    }
  } catch {
    /* Server errors remain visible in the main application. */
  }
})
async function complete() {
  if (password.value !== repeat.value) {
    error.value = 'Passwörter stimmen nicht überein'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const response = await fetch('/api/setup/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-FoxAir-Admin': '1' },
      body: JSON.stringify({ code: code.value, password: password.value }),
    })
    const data = await response.json()
    if (!response.ok)
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Einrichtung fehlgeschlagen')
    required.value = false
    code.value = ''
    password.value = ''
    repeat.value = ''
    emit('completed')
  } catch (failure) {
    error.value = String(failure)
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <div v-if="required" class="setup-overlay">
    <dialog
      ref="modal"
      @cancel.prevent
      class="setup-wizard panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="setup-title"
    >
      <h1 id="setup-title">FoxAir zum ersten Mal einrichten</h1>
      <p>
        Lege dein Administrationspasswort fest. Den einmaligen Einrichtungscode erhältst du direkt
        auf deinem Server.
      </p>
      <code>{{
        container
          ? 'docker compose exec foxair-web python -m backend.setup'
          : 'cd /opt/foxair-web/app && sudo -u foxair-web /opt/foxair-web/venv/bin/python -m backend.setup'
      }}</code>
      <p>
        Benutzername: <strong>admin</strong>.
        <template v-if="lanHttp">
          Lokales HTTP · Passwort nur im eigenen, vertrauenswürdigen LAN eingeben.</template
        >
      </p>
      <p v-if="!secure" class="read-error">
        Einrichtung nur über HTTPS oder einen lokalen SSH-Tunnel.
      </p>
      <form @submit.prevent="complete">
        <fieldset :disabled="!secure || busy">
          <label
            >Einrichtungscode<input
              class="settings-input"
              v-model="code"
              required
              autocomplete="off"
          /></label>
          <label
            >Neues Passwort<input
              class="settings-input"
              type="password"
              v-model="password"
              minlength="12"
              maxlength="256"
              required
              autocomplete="new-password"
          /></label>
          <label
            >Passwort wiederholen<input
              class="settings-input"
              type="password"
              v-model="repeat"
              minlength="12"
              required
              autocomplete="new-password"
          /></label>
          <p v-if="error" class="read-error" role="alert">{{ error }}</p>
          <button class="main-action" :disabled="busy">
            {{ busy ? 'Einrichtung läuft …' : 'Administrationskonto einrichten' }}
          </button>
        </fieldset>
      </form>
    </dialog>
  </div>
</template>
