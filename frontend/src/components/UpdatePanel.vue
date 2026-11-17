<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { api } from '../api'
import type { UpdateStatus } from '../api'
const props = defineProps<{ admin: boolean; secure: boolean }>()
const updateInfo = ref<UpdateStatus | null>(null)
const updateLoading = ref(false)
const updateRequesting = ref(false)
const updateError = ref('')
const updateMessage = ref('')
async function loadGitUpdateStatus() {
  updateLoading.value = true
  updateError.value = ''
  try {
    updateInfo.value = await api.updateStatus()
  } catch (e) {
    updateError.value = e instanceof Error ? e.message : 'Update-Status nicht erreichbar'
  } finally {
    updateLoading.value = false
  }
}
async function submitGitUpdate() {
  if (!props.secure || !props.admin) {
    updateError.value = 'HTTPS und Web-Administrationspasswort erforderlich.'
    return
  }
  updateRequesting.value = true
  updateError.value = ''
  updateMessage.value = ''
  try {
    await api.requestUpdate('')
    updateMessage.value =
      'Update angefordert. Der getrennte FoxAir-Updater prüft und installiert den passenden Git-Build. Die Web-App kann dabei kurz neu starten.'
    // Do not claim an installation succeeded: completion is observed separately.
  } catch (e) {
    updateError.value = e instanceof Error ? e.message : 'Update-Anforderung fehlgeschlagen'
  } finally {
    updateRequesting.value = false
  }
}

onMounted(loadGitUpdateStatus)
watch(
  () => props.admin,
  () => {
    void loadGitUpdateStatus()
  },
)
</script>
<template>
  <section class="settings-panel panel">
    <div class="section-head">
      <div>
        <span class="section-caption">VERSIONEN / GITHUB</span>
        <h2>FoxAir-Web aktualisieren</h2>
      </div>
      <RefreshCw :size="22" />
    </div>
    <p class="section-hint">
      Der Update-Hilfsdienst aktualisiert ausschließlich FoxAir-Web von GitHub und verwendet
      denselben geprüften Build wie <code>scripts/update.sh</code>. Er wird einmalig im LXC
      installiert.
    </p>
    <div class="update-versions">
      <div>
        <span>Installierter Commit</span
        ><strong>{{ updateInfo?.current?.slice(0, 10) || '—' }}</strong>
      </div>
      <div>
        <span>GitHub main</span
        ><strong>{{ updateInfo?.remote?.slice(0, 10) || 'nicht erreichbar' }}</strong>
      </div>
      <div>
        <span>Aktiver Web-Build</span
        ><strong>{{ updateInfo?.deployed?.slice(0, 10) || 'unbekannt' }}</strong>
      </div>
      <div>
        <span>GitHub web-dist</span
        ><strong>{{ updateInfo?.remote_build?.slice(0, 10) || 'noch nicht erreichbar' }}</strong>
      </div>
      <div>
        <span>Hilfsdienst</span
        ><strong>{{ updateInfo?.installed ? 'Bereit' : 'Nicht eingerichtet' }}</strong>
      </div>
      <div>
        <span>Status</span
        ><strong>{{
          updateInfo?.running
            ? 'Update läuft'
            : updateInfo?.pending
              ? 'Anforderung wartet'
              : updateInfo?.last_result || '—'
        }}</strong>
      </div>
    </div>
    <p v-if="updateInfo?.remote && updateInfo?.deployed === updateInfo.remote" class="success-text">
      <strong>Alles aktuell – neueste Web-Version installiert.</strong>
    </p>
    <p v-else-if="updateInfo?.remote && updateInfo?.deployed !== updateInfo.remote" class="notice">
      <strong
        >Neue Version verfügbar{{
          updateInfo.build_ready ? ' – bereit zur Installation' : ' – Build läuft noch'
        }}.</strong
      >
    </p>
    <p v-if="updateInfo?.update_available" class="success-text">
      Update erforderlich oder aktiver Web-Build ist noch nicht synchronisiert.
    </p>
    <p v-if="updateInfo?.remote && !updateInfo?.build_ready" class="section-hint">
      GitHub Actions baut noch den passenden Web-Stand. Der Updateknopf ist bis zur Fertigstellung
      gesperrt.
    </p>
    <p
      v-else-if="updateInfo?.remote && updateInfo?.current === updateInfo?.remote"
      class="section-hint"
    >
      Installierter Code entspricht dem aktuellen main-Commit.
    </p>
    <p v-if="!updateInfo?.installed" class="section-hint">
      Einmalig als root im LXC: <code>bash scripts/install_web_update.sh</code>
    </p>
    <div class="update-actions">
      <button
        type="button"
        class="outlined-action"
        :disabled="updateLoading"
        @click="loadGitUpdateStatus"
      >
        <RefreshCw :size="16" :class="{ spinning: updateLoading }" /> GitHub-Version prüfen
      </button>
      <button
        type="button"
        class="main-action"
        :disabled="
          !updateInfo?.installed ||
          !updateInfo?.build_ready ||
          updateInfo?.running ||
          updateInfo?.pending ||
          !admin ||
          !secure ||
          updateRequesting
        "
        @click="submitGitUpdate"
      >
        <RefreshCw :size="16" :class="{ spinning: updateRequesting }" />
        {{ updateRequesting ? 'Fordere Update an …' : 'Jetzt über GitHub aktualisieren' }}
      </button>
    </div>
    <p v-if="updateMessage" class="success-text">{{ updateMessage }}</p>
    <p v-if="updateError" class="read-error">{{ updateError }}</p>
    <p class="section-hint">
      Für Updates oben rechts als Administrator anmelden. Die Anmeldung bleibt bis zu 30 Tage
      erhalten, auch bei einem Serverneustart. Der Installationserfolg wird durch die nächste
      Statusprüfung bestätigt.
    </p>
  </section>
</template>
