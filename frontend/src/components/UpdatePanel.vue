<script setup lang="ts">
import { ref } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { api } from '../api'
import type { UpdateStatus } from '../api'
const props = defineProps<{
  admin: boolean
  secure: boolean
  updateInfo: UpdateStatus | null
  version?: string
  updateLoading?: boolean
  checkError?: string
  checkedAt?: Date | null
}>()
const emit = defineEmits<{ refresh: [] }>()
const updateRequesting = ref(false)
const updateError = ref('')
const updateMessage = ref('')
async function submitGitUpdate() {
  if (
    !props.secure ||
    !props.admin ||
    !['release', 'work'].includes(props.updateInfo?.update_mode || '')
  ) {
    updateError.value = 'Für Updates als Administrator über einen zugelassenen Zugang anmelden.'
    return
  }
  updateRequesting.value = true
  updateError.value = ''
  updateMessage.value = ''
  try {
    await api.requestUpdate('')
    updateMessage.value =
      'Update angefordert. FoxAir prüft und installiert den passenden Stand. Die Web-App kann dabei kurz neu starten.'
    emit('refresh')
  } catch (e) {
    updateError.value = e instanceof Error ? e.message : 'Update-Anforderung fehlgeschlagen'
  } finally {
    updateRequesting.value = false
  }
}
</script>
<template>
  <section
    id="settings-update"
    class="settings-panel panel"
    aria-labelledby="settings-update-title"
  >
    <div class="section-head">
      <div>
        <span class="section-caption">VERSIONEN / GITHUB</span>
        <h2 id="settings-update-title" tabindex="-1">FoxAir-Web aktualisieren</h2>
      </div>
      <RefreshCw :size="22" />
    </div>
    <p v-if="updateInfo?.update_mode === 'container'" class="section-hint">
      Container über Docker Compose oder Portainer aktualisieren. Keine Host-Updates aus der
      Web-App.
    </p>
    <p v-else-if="updateInfo?.update_mode === 'work'" class="section-hint">
      Testinstallation auf work. Ein Update wird verfügbar, sobald der passende Frontend-Build
      fertig ist.
    </p>
    <p v-else class="section-hint">
      Updates verwenden ausschließlich vollständige freigegebene Releases mit zusammengehörigem
      Backend, Frontend und Docker-Version.
    </p>
    <p v-if="updateInfo && !updateInfo.build_consistent" class="notice">
      Entwicklungs-/Legacy-Installation oder Backend und Frontend noch nicht gemeinsam
      bereitgestellt.
    </p>
    <div class="update-versions">
      <div>
        <span>Installierte Version</span
        ><strong>{{ version || updateInfo?.version || '—' }}</strong>
      </div>
      <div>
        <span>Verfügbare Version</span><strong>{{ updateInfo?.available_version || '—' }}</strong>
      </div>
      <div>
        <span>Build-Kanal</span><strong>{{ updateInfo?.channel || '—' }}</strong>
      </div>
    </div>
    <p v-if="updateInfo?.notes_url">
      <a :href="updateInfo.notes_url" target="_blank" rel="noopener">Release Notes öffnen</a>
    </p>
    <details>
      <summary>Technische Build-Details</summary>
      <div class="update-versions">
        <div>
          <span>Installierter Commit</span
          ><strong>{{ updateInfo?.current?.slice(0, 10) || '—' }}</strong>
        </div>
        <div>
          <span>Release-Commit</span
          ><strong>{{ updateInfo?.remote?.slice(0, 10) || 'nicht erreichbar' }}</strong>
        </div>
        <div>
          <span>Aktiver Web-Build</span
          ><strong>{{ updateInfo?.deployed?.slice(0, 10) || 'unbekannt' }}</strong>
        </div>
        <div>
          <span>Release-Frontend</span
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
    </details>
    <p v-if="updateInfo?.update_available" class="notice">
      <strong v-if="updateInfo.update_mode === 'release'"
        >Freigegebenes Release {{ updateInfo.available_version }} ist verfügbar.</strong
      >
      <strong v-else>Update {{ updateInfo.available_version }} ist verfügbar.</strong>
    </p>
    <p v-else-if="updateInfo?.check_status === 'building'" class="notice">
      Der passende Web-Build für work wird noch erstellt.
    </p>
    <p v-else-if="updateInfo?.check_status === 'paused'" class="section-hint">
      Updateprüfung pausiert.
    </p>
    <p v-else-if="updateInfo?.check_status === 'unavailable'" class="section-hint">
      Updatequelle derzeit nicht verfügbar.
    </p>
    <p
      v-else-if="updateInfo?.available_version && updateInfo?.build_consistent"
      class="success-text"
    >
      <strong v-if="updateInfo.update_mode === 'release'"
        >Kein neueres freigegebenes Release verfügbar.</strong
      >
      <strong v-else>Kein Update verfügbar.</strong>
    </p>
    <p
      v-if="updateInfo?.update_mode !== 'container' && updateInfo && !updateInfo.installed"
      class="section-hint"
    >
      Einmalig auf dem Server als root:
      <code>bash /opt/foxair-web/app/scripts/install_web_update.sh</code>
    </p>
    <div class="update-actions">
      <button
        type="button"
        class="outlined-action"
        :disabled="updateLoading"
        @click="emit('refresh')"
      >
        <RefreshCw :size="16" :class="{ spinning: updateLoading }" /> Jetzt auf Updates prüfen
      </button>
      <button
        type="button"
        v-if="updateInfo && updateInfo.update_mode !== 'container'"
        class="main-action"
        :disabled="
          !updateInfo?.update_available ||
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
    <p v-if="checkedAt" class="section-hint">
      Zuletzt geprüft {{ checkedAt.toLocaleString('de-DE') }} · Prüfung alle 15 Minuten bei
      geöffneter App.
    </p>
    <p v-if="checkError" class="read-error">{{ checkError }}</p>
    <p v-if="updateError" class="read-error">{{ updateError }}</p>
    <p v-if="updateInfo && updateInfo.update_mode !== 'container'" class="section-hint">
      Für Updates oben rechts als Administrator anmelden. Die Anmeldung bleibt bis zu 30 Tage
      erhalten, auch bei einem Serverneustart. Der Installationserfolg wird durch die nächste
      Statusprüfung bestätigt.
    </p>
  </section>
</template>
