<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Globe } from 'lucide-vue-next'
import { api, type LanAccess } from '../api'

const state = ref<LanAccess | null>(null)
const names = ref('')
const saving = ref(false)
const error = ref('')
const notice = ref('')

onMounted(async () => {
  try {
    state.value = await api.lanAccess()
    names.value = state.value.hosts.join(', ')
  } catch (cause) {
    error.value = (cause as Error).message
  }
})

async function save() {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const hosts = names.value
      .split(',')
      .map((name) => name.trim())
      .filter(Boolean)
    state.value = await api.saveLanAccess(hosts)
    names.value = state.value.hosts.join(', ')
    notice.value = 'Gespeichert. Die Namen sind sofort freigegeben.'
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section v-if="state?.enabled || error" class="settings-panel panel">
    <div class="section-head">
      <h2>Webzugriff</h2>
      <Globe :size="22" />
    </div>
    <form v-if="state?.enabled" @submit.prevent="save">
      <label for="lan-hostnames" class="field-label">Zusätzliche Hostnamen</label>
      <input
        id="lan-hostnames"
        v-model="names"
        class="settings-input"
        type="text"
        aria-describedby="lan-hostnames-hint"
        placeholder="waermepumpe.home.arpa, foxair.example.org"
        autocomplete="off"
        autocapitalize="none"
        spellcheck="false"
        :disabled="saving"
      />
      <p id="lan-hostnames-hint" class="section-hint">
        Mehrere Namen mit Komma trennen. Gib die Namen ein, die du im Browser verwendest.
      </p>
      <p v-if="state.configured_hosts.length" class="section-hint">
        Bereits eingerichtet: {{ state.configured_hosts.join(', ') }}
      </p>
      <button type="submit" class="outlined-action" :disabled="saving">
        {{ saving ? 'Wird gespeichert …' : 'Namen speichern' }}
      </button>
    </form>
    <p v-if="error" class="read-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="section-hint" role="status">{{ notice }}</p>
  </section>
</template>
