<script setup lang="ts">
import { onMounted, ref } from 'vue'
type UserRow = {
  username: string
  role: string
  enabled: boolean
  allowed_registers: number[]
  fallback?: boolean
}
type SessionRow = { id: string; username: string; expires: number; current: boolean }
type AuditRow = {
  user: string
  status: number | string
  path: string
  timestamp: string
  request: unknown
  result: unknown
}
const users = ref<UserRow[]>([]),
  sessions = ref<SessionRow[]>([]),
  audit = ref<AuditRow[]>([])
const dialog = ref<HTMLDialogElement | null>(null)
const message = ref(''),
  busy = ref(false),
  guest = ref(true),
  mapping = ref('')
const name = ref(''),
  role = ref('reader'),
  password = ref(''),
  enabled = ref(true),
  registers = ref('')
async function call(path: string, body?: unknown) {
  const response = await fetch('/api/accounts' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-FoxAir-Admin': '1', 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json()
  if (!response.ok)
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Auftrag fehlgeschlagen')
  return data
}
async function load() {
  const data = await call('')
  users.value = data.users
  guest.value = data.guest_read
  mapping.value = Object.entries(data.sso_mapping)
    .map(([a, b]) => a + '=' + b)
    .join('\n')
  sessions.value = (await call('/sessions')).items
  audit.value = (await call('/audit')).items || []
}
async function run(action: () => Promise<unknown>) {
  busy.value = true
  message.value = ''
  try {
    await action()
    await load()
    message.value = 'Gespeichert'
  } catch (e) {
    message.value = String(e)
  } finally {
    busy.value = false
    password.value = ''
  }
}
function edit(u: UserRow) {
  name.value = u.username
  role.value = u.role
  enabled.value = u.enabled
  registers.value = (u.allowed_registers || []).join(',')
  password.value = ''
}
function save() {
  return run(() =>
    call('/user', {
      username: name.value,
      role: role.value,
      enabled: enabled.value,
      password: password.value,
      allowed_registers: registers.value
        ? registers.value.split(',').map((x) => Number(x.trim()))
        : [],
    }),
  )
}
function policy() {
  return run(async () => {
    const pairs = mapping.value
      .split('\n')
      .filter((x) => x.trim())
      .map((x) => x.split('=').map((x) => x.trim()))
    if (pairs.some((x) => x.length !== 2 || !x[0] || !x[1]))
      throw new Error('Zuordnung als SSO-Name=lokaler Benutzer eingeben')
    await call('/policy', { guest_read: guest.value, sso_mapping: Object.fromEntries(pairs) })
  })
}
const backupPassword = ref(''),
  archive = ref('')
async function exportBackup() {
  await run(async () => {
    const result = await call('/backup', { password: backupPassword.value })
    const url = URL.createObjectURL(new Blob([result.archive], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'foxair-backup.encrypted.json'
    a.click()
    URL.revokeObjectURL(url)
    backupPassword.value = ''
  })
}
async function readBackup(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) archive.value = await file.text()
}
async function restoreBackup() {
  if (
    !confirm(
      'Einstellungen und Benutzer aus dieser Sicherung ersetzen? Alle Sitzungen werden beendet.',
    )
  )
    return
  await run(async () => {
    await call('/restore', { password: backupPassword.value, archive: archive.value })
    backupPassword.value = ''
    archive.value = ''
    window.location.reload()
  })
}
onMounted(async () => {
  try {
    await load()
  } catch (error) {
    message.value = String(error)
  }
})
</script>
<template>
  <section class="settings-panel panel account-management">
    <h2>Benutzer &amp; Berechtigungen</h2>
    <p>
      Konten, Rollen, SSO-Zuordnungen, Sitzungen, Änderungsprotokoll und verschlüsselte Sicherungen
      verwalten.
    </p>
    <button type="button" class="outlined-action" @click="dialog?.showModal()">
      Benutzerverwaltung öffnen
    </button>
  </section>
  <dialog
    ref="dialog"
    class="connection-dialog panel account-management"
    aria-labelledby="accounts-title"
    @click.self="dialog?.close()"
  >
    <div class="connection-dialog-content">
      <header class="connection-dialog-header">
        <h2 id="accounts-title">Benutzer &amp; Berechtigungen</h2>
        <button type="button" class="outlined-action" @click="dialog?.close()">Schließen</button>
      </header>
      <p>
        Leser sehen Messwerte. Bediener dürfen nur ausdrücklich freigegebene Register ändern.
        Administratoren verwalten die Anwendung. Das Konto admin bleibt als Notfallzugang erhalten.
      </p>
      <p v-if="message" role="status">{{ message }}</p>
      <div class="transport-options">
        <button
          v-for="u in users"
          :key="u.username"
          class="outlined-action"
          :disabled="u.fallback"
          @click="edit(u)"
        >
          {{ u.username }} · {{ u.role }} · {{ u.enabled ? 'aktiv' : 'gesperrt' }}
        </button>
      </div>
      <form @submit.prevent="save">
        <label
          >Benutzername<input
            class="settings-input"
            v-model="name"
            required
            autocomplete="off" /></label
        ><label
          >Rolle<select class="settings-input" v-model="role">
            <option value="reader">Leser</option>
            <option value="operator">Bediener</option>
            <option value="admin">Administrator</option>
          </select></label
        ><label
          >Neues Passwort (leer = unverändert oder nur SSO)<input
            class="settings-input"
            type="password"
            v-model="password"
            autocomplete="new-password" /></label
        ><label
          >Freigegebene Modbus-Register, mit Komma getrennt<input
            class="settings-input"
            v-model="registers"
            placeholder="z. B. 1012,1158" /></label
        ><label><input type="checkbox" v-model="enabled" /> Konto aktiv</label
        ><button class="main-action" :disabled="busy">Benutzer speichern</button>
      </form>
      <h3>Authelia &amp; Gastzugriff</h3>
      <label
        >Zuordnung: eine Zeile pro Benutzer<textarea
          class="settings-input"
          v-model="mapping"
          placeholder="sso-name=lokaler-benutzer"
        ></textarea></label
      ><label
        ><input type="checkbox" v-model="guest" /> Messwerte ohne lokale Anmeldung lesen
        erlauben</label
      ><button class="outlined-action" :disabled="busy" @click="policy">
        Zugriffsregeln speichern
      </button>
      <h3>Sitzungen</h3>
      <div v-for="s in sessions" :key="s.id">
        <span
          >{{ s.username }} · bis {{ new Date(s.expires * 1000).toLocaleString() }}
          {{ s.current ? '(diese Sitzung)' : '' }}</span
        ><button
          class="outlined-action"
          :disabled="busy"
          @click="run(() => call('/sessions/revoke', { id: s.id }))"
        >
          Abmelden
        </button>
      </div>
      <h3>Sicherung &amp; Wiederherstellung</h3>
      <p>
        Verschlüsselt Benutzer, Cloud-Zugang und LTE-Einstellungen. Das bestehende Notfallpasswort,
        Proxy-Secrets und SSO-Serverkonfiguration bleiben unverändert. Sicherungspasswort separat
        aufbewahren.
      </p>
      <input
        class="settings-input"
        type="password"
        v-model="backupPassword"
        placeholder="Sicherungspasswort, mindestens 12 Zeichen"
        autocomplete="new-password"
      />
      <button
        class="outlined-action"
        :disabled="busy || backupPassword.length < 12"
        @click="exportBackup"
      >
        Verschlüsselte Sicherung herunterladen
      </button>
      <input type="file" accept="application/json,.json" @change="readBackup" />
      <button
        class="outlined-action"
        :disabled="busy || !archive || backupPassword.length < 12"
        @click="restoreBackup"
      >
        Sicherung wiederherstellen
      </button>
      <h3>Änderungsprotokoll</h3>
      <details v-for="(a, i) in audit" :key="i">
        <summary>{{ a.user }} · {{ a.status }} · {{ a.path }}</summary>
        <pre style="white-space: pre-wrap; overflow-wrap: anywhere">{{
          JSON.stringify(a, null, 2)
        }}</pre>
      </details>
    </div>
  </dialog>
</template>

<style scoped>
.account-management form {
  display: grid;
  gap: 12px;
  margin: 20px 0;
}
.account-management label {
  display: grid;
  gap: 6px;
  margin: 10px 0;
}
.account-management label:has(input[type='checkbox']) {
  display: flex;
  align-items: center;
}
.account-management p {
  font-size: 13px;
  line-height: 1.6;
}
.account-management button {
  margin: 5px 5px 5px 0;
  white-space: normal;
}
.account-management details {
  padding: 10px 0;
  border-bottom: 1px solid #eceef1;
  font-size: 12px;
}
.account-management input[type='file'] {
  display: block;
  max-width: 100%;
  margin: 12px 0;
}
</style>
